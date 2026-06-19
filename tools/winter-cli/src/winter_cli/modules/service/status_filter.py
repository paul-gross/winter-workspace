"""Backstop filter for the winter service status document.

After parsing the orchestrator's JSON output into a ``StatusDocument``, winter
applies a pattern-based backstop filter when the user supplied one or more
``<env>/<service>`` segment-glob patterns.  Services whose ``<env>/<name>``
does not match any pattern are dropped; envs that become empty are dropped too.
When no patterns are given the document is returned unchanged.
"""

from __future__ import annotations

from winter_cli.modules.service.status_models import EnvStatus, ServiceStatus, StatusDocument
from winter_cli.modules.workspace.pattern_match import matches_any_pattern


def filter_status(doc: StatusDocument, patterns: tuple[str, ...]) -> StatusDocument:
    """Return a filtered copy of *doc* keeping only services matching *patterns*.

    If *patterns* is empty the original document is returned unchanged (identity).

    For each env, services are kept when
    ``matches_any_pattern(env.env, svc.name, patterns)`` is True.  Envs whose
    filtered service list is empty are dropped entirely.  The resulting
    ``StatusDocument`` always contains only the envs and services that survived
    the filter.
    """
    if not patterns:
        return doc

    filtered_envs: list[EnvStatus] = []
    for env in doc.envs:
        kept: list[ServiceStatus] = [svc for svc in env.services if matches_any_pattern(env.env, svc.name, patterns)]
        if kept:
            filtered_envs.append(
                EnvStatus(
                    env=env.env,
                    session=env.session,
                    port_base=env.port_base,
                    services=tuple(kept),
                )
            )

    return StatusDocument(envs=tuple(filtered_envs))
