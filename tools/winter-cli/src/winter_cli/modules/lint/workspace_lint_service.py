from __future__ import annotations

import os

from winter_cli.config.models import WorkspaceConfig
from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.lint.finding_parser import parse_lint_output
from winter_cli.modules.lint.models import LintCheckOutcome, LintFinding, LintScope, LintStatus
from winter_cli.modules.lint.scope_env import WINTER_CLI_VAR, lint_scope_env

# Source label shown in `winter lint` output for the workspace-level check.
# Matches the doctor workspace-probe label so both surfaces read consistently.
WORKSPACE_SOURCE = "project"


class WorkspaceLintService:
    """Invokes the workspace's own `lint` script declared in `.winter/config.toml`.

    Mirrors `doctor`'s `WorkspaceProbeService` for the lint surface: an opt-in
    executable script for ecosystem-general checks the workspace owns but no
    single extension does. Returns one `LintCheckOutcome` when a script is
    declared (even if it finds nothing), or `None` when the workspace declares
    no `lint` field.
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        fs: IFilesystemReader,
        subprocess_runner: ISubprocessRunner,
        winter_cli_path: str,
    ) -> None:
        self._config = config
        self._fs = fs
        self._subprocess = subprocess_runner
        self._winter_cli_path = winter_cli_path

    def run(self, scope: LintScope) -> LintCheckOutcome | None:
        if not self._config.lint:
            return None

        env = os.environ.copy()
        env["WINTER_WORKSPACE_DIR"] = str(self._config.workspace_root)
        env[WINTER_CLI_VAR] = self._winter_cli_path
        env.update(lint_scope_env(scope))

        findings: list[LintFinding] = []
        for script_rel in self._config.lint:
            findings.extend(self._run_script(script_rel, env))
        return LintCheckOutcome(source=WORKSPACE_SOURCE, findings=findings)

    def _run_script(self, script_rel: str, env: dict[str, str]) -> list[LintFinding]:
        script_path = (self._config.workspace_root / script_rel).resolve()
        try:
            script_path.relative_to(self._config.workspace_root.resolve())
        except ValueError:
            return [self._fail_finding(f"lint path `{script_rel}` escapes the workspace directory")]
        if not self._fs.is_file(script_path):
            return [self._fail_finding(f"lint script not found at {script_path}")]
        if not self._fs.access_x_ok(script_path):
            return [
                self._fail_finding(f"lint script not executable: {script_path}", remediation=f"chmod +x {script_path}")
            ]
        try:
            result = self._subprocess.run([str(script_path)], cwd=self._config.workspace_root, env=env)
        except OSError as exc:
            return [self._fail_finding(f"failed to invoke lint: {exc}")]
        return parse_lint_output(WORKSPACE_SOURCE, result.stdout, result.stderr, result.returncode)

    @staticmethod
    def _fail_finding(message: str, remediation: str | None = None) -> LintFinding:
        return LintFinding(
            source=WORKSPACE_SOURCE,
            check="lint",
            status=LintStatus.fail,
            message=message,
            remediation=remediation,
        )
