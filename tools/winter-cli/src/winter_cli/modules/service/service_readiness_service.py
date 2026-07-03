"""Readiness gate for ``winter service up --wait``.

After ``up`` has dispatched, this service polls the orchestrator's ``status``
action (via :class:`ServiceStatusService.collect`, the same parse/merge path
``winter service status`` uses) and blocks until **no in-scope service reports
``health: "unhealthy"``** — every service is ``"healthy"`` or ``"unknown"`` (a
service with no declared probe reports ``"unknown"`` and must not block) — or a
timeout elapses.

This is entirely winter-side: it adds no orchestrator action, env var, or argv
token. It only consumes the ``health`` field already in the status contract.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable

from winter_cli.modules.service.service_status_service import ServiceStatusService
from winter_cli.modules.service.status_models import StatusDocument

# Default ceiling for ``--wait`` when ``--timeout`` is not supplied.
DEFAULT_WAIT_TIMEOUT_S: float = 120.0

# Delay between status polls while waiting for readiness.
DEFAULT_POLL_INTERVAL_S: float = 1.0

_UNHEALTHY = "unhealthy"


@dataclasses.dataclass(frozen=True)
class ReadinessResult:
    """Outcome of a readiness wait.

    ``ready`` is True when no in-scope service reported ``unhealthy`` before the
    timeout. ``unhealthy`` lists the ``<env>/<service>`` identifiers still
    unhealthy when the wait gave up (empty when ``ready``).
    """

    ready: bool
    unhealthy: tuple[str, ...]


class ServiceReadinessService:
    """Polls service health until readiness or timeout.

    ``status_service`` supplies the merged, filtered status document each poll.
    ``sleep`` and ``monotonic`` are injected (defaulting to the stdlib) so tests
    can drive the clock without real delays.
    """

    def __init__(
        self,
        status_service: ServiceStatusService,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    ) -> None:
        self._status_service = status_service
        self._sleep = sleep
        self._monotonic = monotonic
        self._poll_interval_s = poll_interval_s

    def wait(self, patterns: tuple[str, ...], timeout_s: float) -> ReadinessResult:
        """Poll ``status`` for *patterns* until no service is unhealthy, or *timeout_s* elapses.

        *patterns* scope the poll exactly like ``status`` PATTERNS: a bare env
        (``alpha``) expands to ``alpha/*``, ``workspace`` to ``workspace/*``, and
        a glob (``al*``) or multiple patterns gate readiness across every matched
        scope in one poll cycle. Returns as soon as a poll shows no unhealthy
        service (the common case completes on the first poll). On timeout, returns
        the still-unhealthy identifiers so the caller can name them.
        """
        deadline = self._monotonic() + timeout_s

        while True:
            doc = self._status_service.collect(patterns)
            unhealthy = _unhealthy_services(doc)
            if not unhealthy:
                return ReadinessResult(ready=True, unhealthy=())
            if self._monotonic() >= deadline:
                return ReadinessResult(ready=False, unhealthy=unhealthy)
            self._sleep(self._poll_interval_s)


def _unhealthy_services(doc: StatusDocument | None) -> tuple[str, ...]:
    """Return ``<env>/<service>`` for every service reporting ``health: unhealthy``.

    A ``None`` document (no provider produced a parseable status) yields no
    unhealthy services — there is nothing reporting unhealthy, so the wait does
    not block on it.
    """
    if doc is None:
        return ()
    return tuple(f"{env.env}/{svc.name}" for env in doc.envs for svc in env.services if svc.health == _UNHEALTHY)
