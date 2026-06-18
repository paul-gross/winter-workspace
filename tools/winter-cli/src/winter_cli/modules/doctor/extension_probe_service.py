from __future__ import annotations

import os

from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.doctor.models import ProbeResult, ProbeStatus
from winter_cli.modules.doctor.probe_parser import parse_probe_output
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import RepoError, StandaloneRepository


class ExtensionProbeService:
    """Invokes each installed extension's `doctor` script and parses NDJSON output.

    Contract:
      - Script runs with `WINTER_WORKSPACE_DIR`, `WINTER_EXT_DIR`, and
        `WINTER_EXT_PREFIX` in the environment, cwd set to the workspace root.
      - Each NDJSON line on stdout becomes one `ProbeResult` tagged with the
        extension's prefix as `source`.
      - Lines that don't parse, or that lack required fields, become a single
        synthetic `warn` result so the issue is visible without aborting the run.
      - A non-zero exit becomes a single `fail` result with stderr as the message.
      - Extensions without a `doctor` field, with a missing script, or with a
        non-executable script are silently skipped (no result emitted) — except
        the non-executable case surfaces as a `fail` so the misconfiguration is
        actionable.
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        fs: IFilesystemReader,
        subprocess_runner: ISubprocessRunner,
        manifest_loader: ExtensionManifestLoader,
    ) -> None:
        self._config = config
        self._fs = fs
        self._subprocess = subprocess_runner
        self._manifest_loader = manifest_loader

    def run(self, standalone_repos: list[StandaloneRepository]) -> list[ProbeResult]:
        if self._config.adopt_extensions == AdoptExtensions.none:
            return []

        results: list[ProbeResult] = []
        for repo in standalone_repos:
            results.extend(self._run_one(repo))
        return results

    def _run_one(self, repo: StandaloneRepository) -> list[ProbeResult]:
        manifest_path = repo.path / EXT_MANIFEST
        if not self._fs.is_file(manifest_path):
            return []
        try:
            manifest = self._manifest_loader.load(repo, manifest_path)
        except RepoError as exc:
            return [
                ProbeResult(
                    source=repo.name,
                    name="manifest",
                    status=ProbeStatus.fail,
                    message=str(exc),
                )
            ]

        if not manifest.doctor:
            return []

        script_path = (repo.path / manifest.doctor).resolve()
        try:
            script_path.relative_to(repo.path.resolve())
        except ValueError:
            return [
                ProbeResult(
                    source=manifest.prefix,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"doctor path `{manifest.doctor}` escapes the extension directory",
                )
            ]
        if not self._fs.is_file(script_path):
            return [
                ProbeResult(
                    source=manifest.prefix,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"doctor script not found at {script_path}",
                )
            ]
        if not self._fs.access_x_ok(script_path):
            return [
                ProbeResult(
                    source=manifest.prefix,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"doctor script not executable: {script_path}",
                    remediation=f"chmod +x {script_path}",
                )
            ]

        env = os.environ.copy()
        env.update(
            {
                "WINTER_WORKSPACE_DIR": str(self._config.workspace_root),
                "WINTER_EXT_DIR": str(repo.path),
                "WINTER_EXT_PREFIX": manifest.prefix,
            }
        )
        try:
            result = self._subprocess.run(
                [str(script_path)],
                cwd=self._config.workspace_root,
                env=env,
            )
        except OSError as exc:
            return [
                ProbeResult(
                    source=manifest.prefix,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"failed to invoke doctor: {exc}",
                )
            ]

        return parse_probe_output(manifest.prefix, result.stdout, result.stderr, result.returncode)
