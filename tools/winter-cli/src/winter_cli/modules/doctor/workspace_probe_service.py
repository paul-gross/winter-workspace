from __future__ import annotations

import os

from winter_cli.config.models import WorkspaceConfig
from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.doctor.models import ProbeResult, ProbeStatus
from winter_cli.modules.doctor.probe_parser import parse_probe_output

# Source label shown in `winter doctor` output for workspace probes.
# Sits between `core` (winter-cli built-ins) and each extension's prefix.
WORKSPACE_SOURCE = "project"


class WorkspaceProbeService:
    """Invokes the workspace's own doctor script declared in `.winter/config.toml`.

    Mirrors `ExtensionProbeService` for the workspace surface: an opt-in
    executable script that emits NDJSON probes for whatever the project
    cares about (database running, .env populated, secrets present, …).
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        fs: IFilesystemReader,
        subprocess_runner: ISubprocessRunner,
    ) -> None:
        self._config = config
        self._fs = fs
        self._subprocess = subprocess_runner

    def run(self) -> list[ProbeResult]:
        if not self._config.doctor:
            return []

        script_path = (self._config.workspace_root / self._config.doctor).resolve()
        try:
            script_path.relative_to(self._config.workspace_root.resolve())
        except ValueError:
            return [
                ProbeResult(
                    source=WORKSPACE_SOURCE,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"doctor path `{self._config.doctor}` escapes the workspace directory",
                )
            ]
        if not self._fs.is_file(script_path):
            return [
                ProbeResult(
                    source=WORKSPACE_SOURCE,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"doctor script not found at {script_path}",
                )
            ]
        if not self._fs.access_x_ok(script_path):
            return [
                ProbeResult(
                    source=WORKSPACE_SOURCE,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"doctor script not executable: {script_path}",
                    remediation=f"chmod +x {script_path}",
                )
            ]

        env = os.environ.copy()
        env["WINTER_WORKSPACE_DIR"] = str(self._config.workspace_root)
        try:
            result = self._subprocess.run(
                [str(script_path)],
                cwd=self._config.workspace_root,
                env=env,
            )
        except OSError as exc:
            return [
                ProbeResult(
                    source=WORKSPACE_SOURCE,
                    name="doctor",
                    status=ProbeStatus.fail,
                    message=f"failed to invoke doctor: {exc}",
                )
            ]

        return parse_probe_output(WORKSPACE_SOURCE, result.stdout, result.stderr, result.returncode)
