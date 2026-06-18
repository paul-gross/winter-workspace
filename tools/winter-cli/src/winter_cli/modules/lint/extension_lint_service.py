from __future__ import annotations

import os

from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.lint.finding_parser import parse_lint_output
from winter_cli.modules.lint.models import LintCheckOutcome, LintFinding, LintScope, LintStatus
from winter_cli.modules.lint.scope_env import WINTER_CLI_VAR, lint_scope_env
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import RepoError, StandaloneRepository


class ExtensionLintService:
    """Invokes each installed extension's `lint` script and parses NDJSON findings.

    The check-side counterpart of `doctor`'s `ExtensionProbeService`. Contract:
      - Script runs with `WINTER_WORKSPACE_DIR`, `WINTER_EXT_DIR`,
        `WINTER_EXT_PREFIX`, and the `WINTER_LINT_*` scope vars in the
        environment, cwd set to the workspace root.
      - Each NDJSON line on stdout becomes one `LintFinding` tagged with the
        extension's prefix as `source`.
      - One `LintCheckOutcome` is returned per extension that declares a `lint`
        script — even when it produces no findings — so the dispatcher can tell
        "no checks contributed" from "checks ran clean".
      - Lines that don't parse, a non-zero exit, a missing/non-executable
        script, or a path that escapes the extension directory all surface as
        findings rather than aborting the run (same shape as the doctor probe).
      - Extensions without a `lint` field, or with no manifest, contribute no
        outcome (silently skipped).
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        fs: IFilesystemReader,
        subprocess_runner: ISubprocessRunner,
        manifest_loader: ExtensionManifestLoader,
        winter_cli_path: str,
    ) -> None:
        self._config = config
        self._fs = fs
        self._subprocess = subprocess_runner
        self._manifest_loader = manifest_loader
        self._winter_cli_path = winter_cli_path

    def run(self, scope: LintScope, standalone_repos: list[StandaloneRepository]) -> list[LintCheckOutcome]:
        if self._config.adopt_extensions == AdoptExtensions.none:
            return []

        outcomes: list[LintCheckOutcome] = []
        for repo in standalone_repos:
            outcome = self._run_one(scope, repo)
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def _run_one(self, scope: LintScope, repo: StandaloneRepository) -> LintCheckOutcome | None:
        manifest_path = repo.path / EXT_MANIFEST
        if not self._fs.is_file(manifest_path):
            return None
        try:
            manifest = self._manifest_loader.load(repo, manifest_path)
        except RepoError as exc:
            return LintCheckOutcome(
                source=repo.name,
                findings=[LintFinding(source=repo.name, check="manifest", status=LintStatus.fail, message=str(exc))],
            )

        if not manifest.lint:
            return None

        env = os.environ.copy()
        env.update(
            {
                "WINTER_WORKSPACE_DIR": str(self._config.workspace_root),
                "WINTER_EXT_DIR": str(repo.path),
                "WINTER_EXT_PREFIX": manifest.prefix,
                WINTER_CLI_VAR: self._winter_cli_path,
            }
        )
        env.update(lint_scope_env(scope))

        findings: list[LintFinding] = []
        for script_rel in manifest.lint:
            findings.extend(self._run_script(script_rel, repo, manifest.prefix, env))
        return LintCheckOutcome(source=manifest.prefix, findings=findings)

    def _run_script(
        self, script_rel: str, repo: StandaloneRepository, prefix: str, env: dict[str, str]
    ) -> list[LintFinding]:
        script_path = (repo.path / script_rel).resolve()
        try:
            script_path.relative_to(repo.path.resolve())
        except ValueError:
            return [self._fail_finding(prefix, f"lint path `{script_rel}` escapes the extension directory")]
        if not self._fs.is_file(script_path):
            return [self._fail_finding(prefix, f"lint script not found at {script_path}")]
        if not self._fs.access_x_ok(script_path):
            return [
                self._fail_finding(
                    prefix, f"lint script not executable: {script_path}", remediation=f"chmod +x {script_path}"
                )
            ]
        try:
            result = self._subprocess.run([str(script_path)], cwd=self._config.workspace_root, env=env)
        except OSError as exc:
            return [self._fail_finding(prefix, f"failed to invoke lint: {exc}")]
        return parse_lint_output(prefix, result.stdout, result.stderr, result.returncode)

    @staticmethod
    def _fail_finding(source: str, message: str, remediation: str | None = None) -> LintFinding:
        return LintFinding(
            source=source,
            check="lint",
            status=LintStatus.fail,
            message=message,
            remediation=remediation,
        )
