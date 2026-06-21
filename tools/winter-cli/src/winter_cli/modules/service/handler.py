from __future__ import annotations

import dataclasses
import sys

from winter_cli.modules.service.models import LogOptions
from winter_cli.modules.service.scope import WORKSPACE_SCOPE
from winter_cli.modules.service.service_dispatch_service import ServiceDispatchService
from winter_cli.modules.service.service_logs_service import ServiceLogsService
from winter_cli.modules.service.service_reporter import IServiceReporter, JsonServiceReporter, StreamServiceReporter
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
        stream_reporter: StreamServiceReporter,
        json_reporter: JsonServiceReporter,
    ) -> None:
        self._dispatch_service = dispatch_service
        self._logs_service = logs_service
        self._status_service = status_service
        self._stream_reporter = stream_reporter
        self._json_reporter = json_reporter

    def _run_up(self, target: str) -> int:
        return self._dispatch_service.dispatch("up", [target])

    def run(self, params: ServiceParams) -> None:
        action = params.action
        if action == "up":
            env = params.env
            if env == WORKSPACE_SCOPE:
                # Direct workspace-up: single dispatch, no recursion.
                exit_code = self._run_up(WORKSPACE_SCOPE)
                if exit_code != 0:
                    sys.exit(exit_code)
            else:
                # Ensure workspace up first (best-effort: run both regardless of result).
                ws_code = self._run_up(WORKSPACE_SCOPE)
                env_code = self._run_up(env) if env is not None else 0
                first_failure = ws_code if ws_code != 0 else env_code
                if first_failure != 0:
                    sys.exit(first_failure)
        elif action == "down":
            # Single dispatch for any target; workspace scope is left running on env-down.
            positionals = [params.env] if params.env is not None else []
            exit_code = self._dispatch_service.dispatch("down", positionals)
            if exit_code != 0:
                sys.exit(exit_code)
        else:
            positionals = list(params.patterns)
            exit_code = self._dispatch_service.dispatch(action, positionals)
            if exit_code != 0:
                sys.exit(exit_code)

    def run_logs(self, options: LogOptions) -> None:
        reporter: IServiceReporter = self._stream_reporter
        exit_code = self._logs_service.stream(options, reporter)
        if exit_code != 0:
            sys.exit(exit_code)

    def run_status(self, options: StatusOptions) -> None:
        reporter: IServiceReporter = self._json_reporter if options.as_json else self._stream_reporter
        exit_code = self._status_service.report(options, reporter)
        if exit_code != 0:
            sys.exit(exit_code)
