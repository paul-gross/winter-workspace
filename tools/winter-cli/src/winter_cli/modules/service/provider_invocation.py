"""Shared helpers for provider invocation: env-dict construction and pattern matching.

``build_provider_env`` builds the WINTER_* environment dict for any provider
subprocess call, merging the current process environment with the five
base extension context variables (including ``WINTER_EXT_CONFIG_DIR`` and
``WINTER_SERVICE_PREFIX``).

``apply_provisioned_env`` overlays a scope's computed env map onto a provider
env dict. Used by the fan-out (up/down) and status matrix to inject scope vars
into the provider subprocess environment.

``service_matches_pattern`` is the segment-aware fnmatch check used by
``restart`` and ``logs`` routing to decide whether a scope-qualified describe
identifier (``<env>/<svc>``, ``*/<svc>``, ``workspace/<svc>``) matches a
user-supplied selection pattern.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from winter_cli.core.extension_invocation import build_extension_env
from winter_cli.modules.service.scope import WORKSPACE_SCOPE

if TYPE_CHECKING:
    from winter_cli.modules.service.service_reporter import IServiceReporter


class IEnvProvisioner(Protocol):
    """Minimal protocol for an object that can compute an env map for a scope."""

    def compute(self, scope: str) -> dict[str, str]: ...


def build_provider_env(provider: Any, workspace_root: Path, service_prefix: str) -> dict[str, str]:
    """Return a copy of os.environ with WINTER_WORKSPACE_DIR/EXT_DIR/EXT_PREFIX/EXT_CONFIG_DIR/SERVICE_PREFIX set.

    ``provider`` must expose ``ext_dir: Path``, ``prefix: str``, and
    ``config_dir: Path``; compatible with both ``ResolvedCapability`` and
    ``ResolvedOrchestrator``.
    """
    return build_extension_env(
        workspace_root=workspace_root,
        ext_dir=provider.ext_dir,
        prefix=provider.prefix,
        config_dir=provider.config_dir,
        service_prefix=service_prefix,
    )


def apply_provisioned_env(merged: dict[str, str], provisioned_env: dict[str, str]) -> dict[str, str]:
    """Overlay *provisioned_env* onto *merged*.

    Returns a new dict; *merged* is not mutated.  When *provisioned_env* is empty
    the base dict is returned unchanged.
    """
    if not provisioned_env:
        return merged
    return {**merged, **provisioned_env}


def provision_scope_env(
    env_provisioner: IEnvProvisioner | None,
    scope: str,
    reporter: IServiceReporter | None,
) -> dict[str, str]:
    """Compute *scope*'s injected env map, degrading to ``{}`` on a config error.

    Returns ``{}`` when *env_provisioner* is ``None`` (no provisioner bound).
    A ``ValueError`` from ``compute`` (e.g. a malformed env-band template)
    is caught and surfaced via ``reporter.env_provision_error`` rather than
    propagating as a raw traceback; the action then proceeds without injecting
    that scope's env (best-effort, mirroring the resilience contract elsewhere).
    """
    if env_provisioner is None:
        return {}
    try:
        return env_provisioner.compute(scope)
    except ValueError as exc:
        if reporter is not None:
            reporter.env_provision_error(scope, str(exc))
        return {}


def up_down_positional(scope: str, cell_pattern: str) -> str:
    """Return the argv positional to dispatch ``up``/``down`` for one matrix cell.

    ``cell_pattern`` is the ``<scope>/*`` or ``<scope>/<svc>`` token computed by
    ``ServiceStatusMatrixService`` for a status cell. up/down broaden the wire
    contract to accept that same scope-qualified form, but winter dispatches the
    bare ``<scope>`` (today's form) whenever the cell carries no real
    service-segment filter — i.e. ``cell_pattern`` is exactly ``"<scope>/*"`` —
    so existing bare-env-only providers keep working for multi-env up/down. A
    real service-segment filter (``"alpha/api"``) is dispatched as the
    scope-qualified pattern verbatim.
    """
    if cell_pattern == f"{scope}/*":
        return scope
    return cell_pattern


def service_matches_pattern(svc_name: str, pattern: str) -> bool:
    """Return True when the describe identifier ``svc_name`` matches ``pattern``.

    ``svc_name`` is a scope-qualified describe identifier as emitted by a provider's
    ``describe`` action — ``<env>/<svc>`` for a concrete env, ``*/<svc>`` for a
    project-scoped (env-agnostic) service, or ``workspace/<svc>`` for a
    workspace-scoped singleton. ``pattern`` is the user selection token.

    Matching is **segment-wise** over the two ``env``/``svc`` positions: the env
    segments must match and the svc segments must match. Each segment comparison is
    bidirectional so a wildcard on *either* side is honoured — the describe side may
    carry ``*`` on the env segment (``*/api`` runs in any env), and the query side
    may carry ``*`` (e.g. the ``<env>/*`` bare-env expansion below).

    The ``workspace`` scope is reserved and distinct from the ``*`` (any-feature-env)
    wildcard: a ``workspace`` query selects only ``workspace/<svc>`` identifiers, and
    a project-scoped ``*/<svc>`` identifier is never pulled into the workspace scope —
    mirroring the catalog's ``contains`` convention.

    Normalisation of a bare (single-segment) token differs by role:
    - A bare **pattern** is an environment query and expands to ``<pattern>/*`` —
      selecting every service in that env.
    - A bare **describe identifier** is treated as env-agnostic (``*/<svc>``),
      matching the scope-qualified convention providers emit.
    """
    d_env, d_svc = _split_describe(svc_name)
    p_env, p_svc = _split_pattern(pattern)
    return _env_matches(d_env, p_env) and _segment_matches(d_svc, p_svc)


def _split_describe(svc_name: str) -> tuple[str, str]:
    """Split a describe identifier into ``(env, svc)``; a bare name is env-agnostic (``*``)."""
    if "/" in svc_name:
        env_seg, svc_seg = svc_name.split("/", 1)
        return env_seg, svc_seg
    return "*", svc_name


def _split_pattern(pattern: str) -> tuple[str, str]:
    """Split a selection pattern into ``(env, svc)``; a bare token is an env → ``<env>/*``."""
    if "/" in pattern:
        env_seg, svc_seg = pattern.split("/", 1)
        return env_seg, svc_seg
    return pattern, "*"


def _env_matches(describe_env: str, pattern_env: str) -> bool:
    """Match the env segment, keeping the reserved ``workspace`` scope out of ``*``.

    When either side names the ``workspace`` scope the match is exact — a
    ``workspace`` query never selects a project-scoped ``*/<svc>`` identifier, and a
    ``*`` (any-feature-env) query never selects a ``workspace/<svc>`` singleton.
    Otherwise the normal bidirectional glob applies.
    """
    if describe_env == WORKSPACE_SCOPE or pattern_env == WORKSPACE_SCOPE:
        return describe_env == pattern_env
    return _segment_matches(describe_env, pattern_env)


def _segment_matches(describe_seg: str, pattern_seg: str) -> bool:
    """Match one segment, honouring a glob wildcard on either side."""
    return fnmatch.fnmatchcase(pattern_seg, describe_seg) or fnmatch.fnmatchcase(describe_seg, pattern_seg)
