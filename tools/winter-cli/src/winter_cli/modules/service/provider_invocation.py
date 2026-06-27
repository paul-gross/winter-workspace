"""Shared helpers for provider invocation: env-dict construction and pattern matching.

``build_provider_env`` builds the WINTER_* environment dict for any provider
subprocess call, merging the current process environment with the four
base extension context variables (including ``WINTER_EXT_CONFIG_DIR``).

``apply_provisioned_env`` overlays a scope's computed env map onto a provider
env dict. Used by the fan-out (up/down) and status matrix to inject scope vars
into the provider subprocess environment.

``service_matches_pattern`` is the segment-aware fnmatch check used by
``restart`` and ``logs`` routing to decide whether a known service name
matches a user-supplied selection pattern.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from winter_cli.core.extension_invocation import build_extension_env

if TYPE_CHECKING:
    from winter_cli.modules.service.service_reporter import IServiceReporter


class IEnvProvisioner(Protocol):
    """Minimal protocol for an object that can compute an env map for a scope."""

    def compute(self, scope: str) -> dict[str, str]: ...


def build_provider_env(provider: Any, workspace_root: Path) -> dict[str, str]:
    """Return a copy of os.environ with WINTER_WORKSPACE_DIR/EXT_DIR/EXT_PREFIX/EXT_CONFIG_DIR set.

    ``provider`` must expose ``ext_dir: Path``, ``prefix: str``, and
    ``config_dir: Path``; compatible with both ``ResolvedCapability`` and
    ``ResolvedOrchestrator``.
    """
    return build_extension_env(
        workspace_root=workspace_root,
        ext_dir=provider.ext_dir,
        prefix=provider.prefix,
        config_dir=provider.config_dir,
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


def service_matches_pattern(svc_name: str, pattern: str) -> bool:
    """Return True when ``svc_name`` matches ``pattern``.

    Handles two forms:
    - Two-segment ``<env>/<svc>`` pattern: only the svc segment is matched
      against ``svc_name`` (the env segment is used for env-scoping at the
      provider level — see dispatch routing).
    - Bare pattern (no ``/``): matched directly against ``svc_name`` via fnmatch.
    """
    if "/" in pattern:
        _env_seg, svc_seg = pattern.split("/", 1)
        return fnmatch.fnmatchcase(svc_name, svc_seg)
    return fnmatch.fnmatchcase(svc_name, pattern)
