from __future__ import annotations

import dataclasses
import sys

from winter_cli.modules.service.models import LogOptions
from winter_cli.modules.service.service_dispatch_service import ServiceDispatchService
from winter_cli.modules.service.service_logs_service import ServiceLogsService
from winter_cli.modules.service.service_status_service import ServiceStatusService
from winter_cli.modules.service.status_models import StatusOptions


@dataclasses.dataclass
class ServiceParams:
    action: str
    # up/down: the target environment name; None for restart (pattern-selected).
    env: str | None = None
    # restart: verbatim <env>/<service> glob patterns forwarded on argv.
    patterns: tuple[str, ...] = ()


class ServiceHandler:
    """Dispatches `winter service <action>` and adopts the entrypoint's exit code.

    For up/down the dispatch argv is `<entrypoint> <action> <env>`. For restart
    the positionals are the verbatim `<env>/<service>` selection PATTERNS forwarded
    unchanged on argv. Status is handled separately via ``run_status`` which
    captures and parses the structured JSON document from the orchestrator.
    The entrypoint's exit code is adopted as the CLI's exit code so a failing
    implementation surfaces as a non-zero `winter` exit.
    """

    def __init__(
        self,
        dispatch_service: ServiceDispatchService,
        logs_service: ServiceLogsService,
        status_service: ServiceStatusService,
    ) -> None:
        self._dispatch_service = dispatch_service
        self._logs_service = logs_service
        self._status_service = status_service

    def run(self, params: ServiceParams) -> None:
        action = params.action
        if action in ("up", "down"):
            positionals = [params.env] if params.env is not None else []
        else:
            positionals = list(params.patterns)
        exit_code = self._dispatch_service.dispatch(action, positionals)
        if exit_code != 0:
            sys.exit(exit_code)

    def run_logs(self, options: LogOptions) -> None:
        exit_code = self._logs_service.stream(options)
        if exit_code != 0:
            sys.exit(exit_code)

    def run_status(self, options: StatusOptions) -> None:
        exit_code = self._status_service.report(options)
        if exit_code != 0:
            sys.exit(exit_code)
