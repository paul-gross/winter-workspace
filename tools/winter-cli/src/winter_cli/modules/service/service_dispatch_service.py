from __future__ import annotations

import os
from pathlib import Path

from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver


class ServiceDispatchService:
    """Dispatches up/down/restart to the registered service orchestrator.

    The orchestrator is invoked as `<entrypoint> <action> [positional...]` (argv),
    with `cwd` at the workspace root. Every dispatch exports `WINTER_WORKSPACE_DIR`,
    `WINTER_EXT_DIR`, and `WINTER_EXT_PREFIX` (matching the doctor/lint/hook
    dispatches).

    For up/down the single positional is `<env>`. For restart the positionals are
    the verbatim `<env>/<service>` selection PATTERNS forwarded unchanged on argv.
    No per-action selection env vars are set here (status is handled separately by
    ServiceStatusService; logs is handled separately by ServiceLogsService).

    The entrypoint's exit code is returned unmodified; stdout/stderr are
    inherited from the parent process (no capture).
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        orchestrator_resolver: ServiceOrchestratorResolver,
        workspace_root: Path,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._orchestrator_resolver = orchestrator_resolver
        self._workspace_root = workspace_root

    def dispatch(self, action: str, positionals: list[str]) -> int:
        """Run the orchestrator's entrypoint and return its exit code unmodified."""
        resolved = self._orchestrator_resolver.resolve()
        cmd = [str(resolved.entrypoint), action, *positionals]
        merged = os.environ.copy()
        merged["WINTER_WORKSPACE_DIR"] = str(self._workspace_root)
        merged["WINTER_EXT_DIR"] = str(resolved.ext_dir)
        merged["WINTER_EXT_PREFIX"] = resolved.prefix
        return self._subprocess_runner.call(cmd, cwd=self._workspace_root, env=merged)
