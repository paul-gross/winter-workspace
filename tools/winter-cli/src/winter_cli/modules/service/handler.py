from __future__ import annotations

import dataclasses
import sys

from winter_cli.modules.service.models import LogOptions
from winter_cli.modules.service.service_dispatch_service import ServiceDispatchService
from winter_cli.modules.service.service_logs_service import ServiceLogsService


@dataclasses.dataclass
class ServiceParams:
    action: str
    env: str
    service_name: str | None = None  # restart only


class ServiceHandler:
    """Dispatches `winter service <action> <env>` and adopts the entrypoint's exit code.

    The dispatch service invokes the orchestrator with a normalized argv
    (`<entrypoint> <action> <env>`) and returns its exit code; the handler
    makes that code the CLI's exit code so a failing implementation surfaces
    as a non-zero `winter` exit.
    """

    def __init__(
        self,
        dispatch_service: ServiceDispatchService,
        logs_service: ServiceLogsService,
    ) -> None:
        self._dispatch_service = dispatch_service
        self._logs_service = logs_service

    def run(self, params: ServiceParams) -> None:
        action = params.action
        if action == "restart":
            extra_env = {"WINTER_SERVICE_NAME": params.service_name or ""}
            exit_code = self._dispatch_service.dispatch(action, params.env, extra_env)
        else:
            exit_code = self._dispatch_service.dispatch(action, params.env)
        if exit_code != 0:
            sys.exit(exit_code)

    def run_logs(self, env: str, options: LogOptions) -> None:
        exit_code = self._logs_service.stream(env, options)
        if exit_code != 0:
            sys.exit(exit_code)
