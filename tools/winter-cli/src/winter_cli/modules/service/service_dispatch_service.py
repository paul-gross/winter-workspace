from __future__ import annotations

from pathlib import Path

from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.capability.models import ResolvedCapability
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver
from winter_cli.modules.service.provider_invocation import (
    build_provider_env,
    service_matches_pattern,
    up_down_positional,
)
from winter_cli.modules.service.service_fan_out_service import FanOutCell, ServiceFanOutService
from winter_cli.modules.service.service_provider_index import ServiceDescribeService
from winter_cli.modules.service.service_readiness_service import DEFAULT_WAIT_TIMEOUT_S
from winter_cli.modules.service.service_reporter import IServiceReporter
from winter_cli.modules.service.service_status_matrix_service import (
    ServiceStatusMatrixService,
    cell_service_patterns,
)


class ServiceDispatchService:
    """Dispatches up/down/restart to the registered service orchestrator(s).

    For ``up`` and ``down``, reuses ``ServiceStatusMatrixService.build_matrix`` to
    enumerate the matched (provider, scope) cells for the user's ``<env>/<service>``
    glob PATTERNS — the same registry-driven enumeration `status` uses — and fans
    them out via ``ServiceFanOutService`` with no readiness gate or ordering
    semantics beyond the matrix's own deterministic cell order.

    For ``restart`` with multiple providers, builds the service-to-provider ownership
    index via ``ServiceDescribeService``, groups matched services by owning provider,
    and dispatches each provider only the services it owns.  With a single provider,
    ``restart`` behaves exactly as before (no ``describe`` call, patterns forwarded
    verbatim).

    For other actions (``describe``, etc.), dispatches to the single resolved provider
    via the orchestrator resolver, as before.

    The orchestrator is invoked as `<entrypoint> <action> [positional...]` (argv),
    with `cwd` at the workspace root. Every dispatch exports `WINTER_WORKSPACE_DIR`,
    `WINTER_EXT_DIR`, `WINTER_EXT_PREFIX`, and `WINTER_SERVICE_PREFIX` (matching the
    doctor/lint/hook dispatches).

    For up/down the positional per cell is the bare scope (no service-segment filter
    matched), the scope-qualified pattern (exactly one real filter matched — see
    ``up_down_positional``), or, when 2+ distinct service-segment filters target the
    same (provider, scope) cell, one FanOutCell per service pattern (``cell_service_patterns``)
    so the provider starts/stops exactly the requested services rather than the whole
    scope (winter#139 MUST-FIX — up/down has no post-dispatch backstop filter like
    `status` does). For restart the positionals are the verbatim `<env>/<service>`
    selection PATTERNS forwarded unchanged on argv. No per-action selection env vars
    are set here (status is handled separately by ServiceStatusService; logs is
    handled separately by ServiceLogsService).

    The entrypoint's exit code is returned unmodified; stdout/stderr are
    inherited from the parent process (no capture).
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        orchestrator_resolver: ServiceOrchestratorResolver,
        fan_out_service: ServiceFanOutService,
        describe_service: ServiceDescribeService,
        matrix_service: ServiceStatusMatrixService,
        workspace_root: Path,
        service_prefix: str,
        reporter: IServiceReporter | None = None,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._orchestrator_resolver = orchestrator_resolver
        self._fan_out_service = fan_out_service
        self._describe_service = describe_service
        self._matrix_service = matrix_service
        self._workspace_root = workspace_root
        self._service_prefix = service_prefix
        self._reporter = reporter

    def dispatch(self, action: str, positionals: list[str], timeout_s: float = DEFAULT_WAIT_TIMEOUT_S) -> int:
        """Run the orchestrator's entrypoint and return its exit code unmodified.

        ``timeout_s`` is only consulted for ``up`` — it is injected into every
        matched cell's provider subprocess env as ``WINTER_SERVICE_TIMEOUT`` (see
        ``ServiceFanOutService.up``), regardless of whether the caller passed
        ``--wait``. It defaults to ``DEFAULT_WAIT_TIMEOUT_S`` so callers that have
        no ``--timeout`` concept of their own (e.g. provision's service check)
        still inject the effective default.
        """
        if action == "up":
            return self._dispatch_up_down("up", tuple(positionals), timeout_s)

        if action == "down":
            return self._dispatch_up_down("down", tuple(positionals))

        if action == "restart":
            return self._dispatch_restart(positionals)

        # For all other actions (describe, …), fall through to the
        # single-provider path via the orchestrator resolver.
        resolved = self._orchestrator_resolver.resolve()
        cmd = [str(resolved.entrypoint), action, *positionals]
        merged = build_provider_env(resolved, self._workspace_root, self._service_prefix)
        return self._subprocess_runner.call(cmd, cwd=self._workspace_root, env=merged)

    def _dispatch_up_down(
        self, action: str, patterns: tuple[str, ...], timeout_s: float = DEFAULT_WAIT_TIMEOUT_S
    ) -> int:
        """Fan ``up``/``down`` out across every matched (provider, scope) cell.

        Reuses ``ServiceStatusMatrixService.build_matrix`` for enumeration — the
        same registry-driven ``IEnvIndexRegistry.all_assignments()`` + (multi-provider)
        ``describe`` ownership rows/columns `status` builds — instead of duplicating
        that logic here. Each cell's dispatch positional is the bare scope when the
        cell carries no service-segment filter, or the scope-qualified pattern when
        it does (``up_down_positional``). No cells matched (e.g. an env name/glob
        that matches no configured env or owning provider) surfaces a diagnostic and
        returns 1, mirroring `status`'s ``no_service_matched`` behaviour.

        Unlike `status`, up/down has no post-dispatch backstop filter — so a scope
        matched by 2+ distinct service-segment patterns (``down alpha/db alpha/api``)
        must NOT collapse to the matrix's whole-scope ``"<scope>/*"`` cell pattern
        (that would dispatch a bare ``down alpha``, stopping the entire scope instead
        of just the named services — winter#139 MUST-FIX). ``cell_service_patterns``
        detects this case and each matched cell is expanded into one FanOutCell per
        service pattern, each carrying its own ``<scope>/<svc>`` positional.

        ``timeout_s`` is forwarded to ``ServiceFanOutService.up`` (ignored for
        ``down``), which injects it as ``WINTER_SERVICE_TIMEOUT`` into every
        cell's provider subprocess env.
        """
        providers = self._orchestrator_resolver.resolve_all()

        def _on_describe_error(name: str, detail: str) -> None:
            if self._reporter is not None:
                self._reporter.describe_parse_error(name, detail)

        cells = self._matrix_service.build_matrix(providers, patterns, on_describe_error=_on_describe_error)

        if not cells:
            if patterns and self._reporter is not None:
                self._reporter.no_service_matched(", ".join(repr(p) for p in patterns))
            return 1

        fan_cells: list[FanOutCell] = []
        for cell in cells:
            svc_patterns = cell_service_patterns(cell.scope, patterns)
            if svc_patterns is not None and len(svc_patterns) >= 2:
                for svc in svc_patterns:
                    fan_cells.append(
                        FanOutCell(
                            provider=cell.provider,
                            scope=cell.scope,
                            positional=f"{cell.scope}/{svc}",
                        )
                    )
            else:
                fan_cells.append(
                    FanOutCell(
                        provider=cell.provider,
                        scope=cell.scope,
                        positional=up_down_positional(cell.scope, cell.cell_pattern),
                    )
                )

        if action == "up":
            return self._fan_out_service.up(fan_cells, timeout_s)
        return self._fan_out_service.down(fan_cells)

    def _dispatch_restart(self, patterns: list[str]) -> int:
        """Route restart to the owning provider(s) based on the service ownership index.

        D1 short-circuit: with a single provider, no describe call is made; the
        provider receives all patterns verbatim.

        With multiple providers, the index is built, each user pattern is matched
        against the known service names, and each provider receives only the
        original pattern tokens that match services it owns (in the user-supplied
        order, deduplicated per provider).  A pattern matching no service in any
        provider emits a diagnostic to stderr.  A provider with no matched
        patterns is not invoked.
        """
        providers = self._orchestrator_resolver.resolve_all()

        # D1: single-provider short-circuit — no describe, forward verbatim.
        if len(providers) == 1:
            provider = providers[0]
            return self._call_provider(provider, "restart", patterns)

        # Multi-provider: build the ownership index.
        index = self._describe_service.build(providers)

        # Collect all known service names from the index.
        known_services = list(index.known_service_names())

        # For each provider, collect the original pattern tokens that match its
        # owned services.  Each pattern is forwarded at most once per provider
        # (deduplicated while preserving first-match order).
        provider_patterns: dict[str, list[str]] = {p.extension_name: [] for p in providers}

        matched_patterns: set[str] = set()
        for pat in patterns:
            for svc_name in known_services:
                owner = index.owner_for(svc_name)
                if owner is None:
                    continue
                if service_matches_pattern(svc_name, pat):
                    matched_patterns.add(pat)
                    owned = provider_patterns[owner.extension_name]
                    if pat not in owned:
                        owned.append(pat)

        # Emit no-match diagnostic for patterns that resolved to no known service.
        unmatched = [p for p in patterns if p not in matched_patterns]
        if unmatched and self._reporter is not None:
            token_list = ", ".join(repr(p) for p in unmatched)
            self._reporter.no_match_diagnostic(token_list)

        # Dispatch each provider that owns matched patterns.
        exit_code = 0
        for provider in providers:
            owned = provider_patterns.get(provider.extension_name, [])
            if not owned:
                continue
            code = self._call_provider(provider, "restart", owned)
            if code != 0 and exit_code == 0:
                exit_code = code

        return exit_code

    def _call_provider(self, provider: ResolvedCapability, action: str, positionals: list[str]) -> int:
        cmd = [str(provider.entrypoint), action, *positionals]
        merged = build_provider_env(provider, self._workspace_root, self._service_prefix)
        return self._subprocess_runner.call(cmd, cwd=self._workspace_root, env=merged)
