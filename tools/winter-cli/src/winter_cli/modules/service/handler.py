from __future__ import annotations

import dataclasses
import sys

from winter_cli.modules.service.models import LogOptions
from winter_cli.modules.service.scope import WORKSPACE_SCOPE
from winter_cli.modules.service.service_dispatch_service import ServiceDispatchService
from winter_cli.modules.service.service_logs_service import ServiceLogsService
from winter_cli.modules.service.service_readiness_service import DEFAULT_WAIT_TIMEOUT_S, ServiceReadinessService
from winter_cli.modules.service.service_reporter import IServiceReporter, JsonServiceReporter, StreamServiceReporter
from winter_cli.modules.service.service_status_service import ServiceStatusService
from winter_cli.modules.service.status_models import StatusOptions


@dataclasses.dataclass
class ServiceParams:
    action: str
    # up/down/restart: one-or-more verbatim <env>/<service> glob patterns
    # forwarded on argv (may be a single bare env/scope name, e.g. "alpha" or
    # "workspace").
    patterns: tuple[str, ...] = ()
    # up only: after dispatching, block until no in-scope service reports
    # `health: unhealthy` (gating on the `status` action) or `timeout_s` elapses.
    # `timeout_s` is only consulted when `wait` is set.
    wait: bool = False
    timeout_s: float = DEFAULT_WAIT_TIMEOUT_S


class ServiceHandler:
    """Dispatches `winter service <action>` and adopts the entrypoint's exit code.

    For up/down/restart the positionals are the verbatim `<env>/<service>`
    selection PATTERNS forwarded on argv; `ServiceDispatchService` enumerates the
    matched (provider, scope) cells for up/down (reusing the status call-matrix)
    and dispatches each cell the bare scope or the scope-qualified pattern per
    ``up_down_positional``. Status is handled separately via ``run_status`` which
    captures and parses the structured JSON document from the orchestrator.
    The entrypoint's exit code is adopted as the CLI's exit code so a failing
    implementation surfaces as a non-zero `winter` exit.
    """

    def __init__(
        self,
        dispatch_service: ServiceDispatchService,
        logs_service: ServiceLogsService,
        status_service: ServiceStatusService,
        readiness_service: ServiceReadinessService,
        stream_reporter: StreamServiceReporter,
        json_reporter: JsonServiceReporter,
    ) -> None:
        self._dispatch_service = dispatch_service
        self._logs_service = logs_service
        self._status_service = status_service
        self._readiness_service = readiness_service
        self._stream_reporter = stream_reporter
        self._json_reporter = json_reporter

    def run(self, params: ServiceParams) -> None:
        action = params.action
        if action == "up":
            self._run_up(params.patterns, params.wait, params.timeout_s)
        elif action == "down":
            # Best-effort fan-out across every matched scope; workspace scope is
            # left running unless explicitly targeted (`down workspace`).
            exit_code = self._dispatch_service.dispatch("down", list(params.patterns))
            if exit_code != 0:
                sys.exit(exit_code)
        else:
            positionals = list(params.patterns)
            exit_code = self._dispatch_service.dispatch(action, positionals)
            if exit_code != 0:
                sys.exit(exit_code)

    def _run_up(self, patterns: tuple[str, ...], wait: bool, timeout_s: float) -> None:
        """Ensure the workspace scope is up, then fan ``up`` out across *patterns*.

        Unless one of *patterns* already targets the workspace scope explicitly
        (a bare ``workspace`` or a ``workspace/<service>`` pattern), a single
        ``up workspace`` dispatch runs first, best-effort (its failure does not
        skip the requested targets — both are attempted, and the first non-zero
        exit code wins). This mirrors the single-env "ensure workspace up first"
        lifecycle policy, generalised across one-or-more matched patterns.
        """
        workspace_explicit = any(p == WORKSPACE_SCOPE or p.startswith(f"{WORKSPACE_SCOPE}/") for p in patterns)
        ws_code = 0
        if not workspace_explicit:
            ws_code = self._dispatch_service.dispatch("up", [WORKSPACE_SCOPE], timeout_s)
        target_code = self._dispatch_service.dispatch("up", list(patterns), timeout_s)
        first_failure = ws_code if ws_code != 0 else target_code
        if first_failure != 0:
            sys.exit(first_failure)
        # Readiness gate (--wait): only reached once the up dispatch(es) succeeded.
        # Scoped to the user-supplied patterns (the implicit workspace-ensure step
        # is never gated).
        if wait:
            self._wait_for_readiness(patterns, timeout_s)

    def _wait_for_readiness(self, patterns: tuple[str, ...], timeout_s: float) -> None:
        """Poll status until services are healthy; exit non-zero on timeout.

        Names the still-unhealthy services on stderr and adopts exit code 1 when
        the timeout elapses with one or more services still ``unhealthy``.
        """
        result = self._readiness_service.wait(patterns, timeout_s)
        if not result.ready:
            label = ", ".join(patterns)
            self._stream_reporter.readiness_timeout(label, timeout_s, result.unhealthy)
            sys.exit(1)

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
