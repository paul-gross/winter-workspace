from __future__ import annotations

import os

from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver


class ServiceDispatchService:
    """Dispatches up/down/status/restart to the registered service orchestrator.

    Each action is invoked as exactly `<entrypoint> <action> <env>` (argv).
    Additional context is conveyed via environment variables:
      - restart: `WINTER_SERVICE_NAME=<service>` (required; the service to bounce)

    The entrypoint's exit code is returned unmodified; stdout/stderr are
    inherited from the parent process (no capture).
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        orchestrator_resolver: ServiceOrchestratorResolver,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._orchestrator_resolver = orchestrator_resolver

    def dispatch(self, action: str, env: str, extra_env: dict[str, str] | None = None) -> int:
        """Run the orchestrator's entrypoint and return its exit code unmodified."""
        entrypoint = self._orchestrator_resolver.resolve()
        cmd = [str(entrypoint), action, env]
        merged = {**os.environ, **extra_env} if extra_env else None
        return self._subprocess_runner.call(cmd, env=merged)
