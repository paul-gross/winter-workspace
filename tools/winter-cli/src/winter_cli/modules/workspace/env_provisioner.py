"""Single source of truth for computing the runtime environment map for a scope.

``EnvProvisionerService.compute(scope)`` returns the complete ``{KEY: VALUE}``
env map that winter injects into every provider subprocess and that
``winter env`` prints as sourceable lines.  All callers — ``winter env``,
``ServiceFanOutService`` (up/down), ``ServiceStatusMatrixService`` (status) —
delegate here so the computation is never duplicated.

Scope semantics
---------------
*scope* is either a feature-env name (e.g. ``"alpha"``) or the reserved literal
``"workspace"``.  The workspace scope uses index 0 (reserved, never allocated to
a feature env); its port base is therefore ``config.port_base_for_index(0)``.

Rendered vars
-------------
The returned map always contains:

    WINTER_ENV                  — scope name
    WINTER_ENV_INDEX            — allocated index as a decimal string
    WINTER_WORKSPACE_PORT_BASE  — port-band start for index 0

For a feature-env scope, additionally:

    WINTER_PORT_BASE            — port-band start for this scope's own band

For the ``"workspace"`` scope, ``WINTER_PORT_BASE`` is deliberately NOT emitted.
The workspace band is exposed ONLY as ``WINTER_WORKSPACE_PORT_BASE`` so the name
carries one meaning everywhere (the per-env band); emitting it under the
workspace value (index-0) would make the name ambiguous across scopes.

Band selection
--------------
``[env.workspace.vars]`` and ``[env.feature.vars]`` are selected by scope:

- **workspace scope**: only ``[env.workspace.vars]`` entries are rendered.
- **feature scope**: ``[env.workspace.vars]`` entries are rendered first (into the
  accumulating dict), then ``[env.feature.vars]`` entries on top.  On a key
  collision the feature-band value wins.  Feature-band templates may reference
  keys already rendered from the workspace band.

Workspace-band template scope invariant
---------------------------------------
``WINTER_PORT_BASE`` is **never** available when rendering ``[env.workspace.vars]``
entries — neither at workspace scope (where it is not in the result at all) nor at
feature scope (where it is excluded from the workspace-band template scope
specifically).  This guarantees a workspace-band entry resolves identically at both
scopes.  Workspace-band templates must use ``WINTER_WORKSPACE_PORT_BASE`` for
workspace-relative port references; a reference to ``${WINTER_PORT_BASE+N}`` in the
workspace band raises ``ValueError`` at any scope (undefined variable).

Feature-band templates do have ``WINTER_PORT_BASE`` in scope (the feature's own port
base) as well as all already-rendered workspace-band keys.

Each entry may reference any earlier key (including the base vars available to that
band's template scope) via ``${NAME}`` or ``${NAME+N}`` tokens.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from winter_cli.modules.service.scope import WORKSPACE_SCOPE
from winter_cli.modules.workspace.env_index import build_env_trio

if TYPE_CHECKING:
    from winter_cli.config.models import WorkspaceConfig
    from winter_cli.modules.workspace.env_index_registry import IEnvIndexRegistry

# Matches ${NAME} or ${NAME+N}: a reference to an in-scope variable, optionally
# plus a non-negative integer offset.  NAME is an env-var-style identifier.
_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:\+(\d+))?\}")
# Matches any ${...} token the reference form did not consume — malformed/unsupported.
_UNKNOWN_TOKEN_RE = re.compile(r"\$\{[^}]*\}")


def _render_env_var_value(band: str, key: str, template: str, scope: dict[str, str]) -> str:
    """Resolve ``${NAME}`` / ``${NAME+N}`` references in *template* against *scope*.

    *band* is a label for error messages (e.g. ``"env.workspace.vars"``).
    *scope* holds the variables visible to this entry: the managed base vars
    (``WINTER_ENV``, ``WINTER_ENV_INDEX``, ``WINTER_PORT_BASE``,
    ``WINTER_WORKSPACE_PORT_BASE``) plus every earlier env-band entry
    already rendered, in declaration order.

    - ``${NAME}``   → NAME's resolved string value.
    - ``${NAME+N}`` → ``int(NAME) + N`` (NAME must parse as an int; N ≥ 0).

    Literal values (no ``${...}`` token) pass through unchanged.  A reference to
    an undefined name, a ``+N`` offset applied to a non-integer value, or any
    other ``${...}`` token is a fatal substitution error — raises ``ValueError``
    with a clear message.
    """

    def _replace(m: re.Match[str]) -> str:
        name, offset = m.group(1), m.group(2)
        if name not in scope:
            raise ValueError(
                f"{band} key {key!r}: reference to undefined variable {name!r} "
                f"— reference a managed base var or an earlier env-band entry."
            )
        value = scope[name]
        if offset is None:
            return value
        try:
            return str(int(value) + int(offset))
        except ValueError:
            raise ValueError(
                f"{band} key {key!r}: cannot apply +{offset} to non-integer value of {name!r} ({value!r})."
            ) from None

    rendered = _REF_RE.sub(_replace, template)

    # Any ${...} the reference form left behind is an unsupported token.
    unknown = _UNKNOWN_TOKEN_RE.search(rendered)
    if unknown:
        raise ValueError(
            f"{band} key {key!r}: unsupported substitution token {unknown.group()!r}. "
            f"Use ${{NAME}} or ${{NAME+N}} referencing a managed base var or an earlier entry."
        )
    return rendered


def _render_band(
    band_label: str,
    band: dict[str, str],
    template_scope: dict[str, str],
    result: dict[str, str],
) -> None:
    """Render all entries in *band* against *template_scope*, accumulating into *result*.

    Each rendered value is added to both *template_scope* (so later entries in
    the same band can reference it) and *result* (the authoritative output map).
    """
    for key, template in band.items():
        value = _render_env_var_value(band_label, key, template, template_scope)
        template_scope[key] = value
        result[key] = value


class EnvProvisionerService:
    """Compute the full runtime environment map for any scope.

    The map is the authoritative set of ``WINTER_*`` variables that winter
    injects into provider subprocesses and that ``winter env`` prints.
    Call :meth:`compute` with a feature-env name or ``"workspace"`` to get the
    complete ``{KEY: VALUE}`` dict.

    Construction::

        EnvProvisionerService(config, registry)
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        registry: IEnvIndexRegistry,
    ) -> None:
        self._config = config
        self._registry = registry

    def compute(self, scope: str) -> dict[str, str]:
        """Return the full env map for *scope*.

        For a feature env this is the env trio (``WINTER_ENV``,
        ``WINTER_ENV_INDEX``, ``WINTER_PORT_BASE``) plus
        ``WINTER_WORKSPACE_PORT_BASE`` and any rendered band entries.

        For ``"workspace"``, ``WINTER_ENV``, ``WINTER_ENV_INDEX``, and
        ``WINTER_WORKSPACE_PORT_BASE`` are returned (index 0, the workspace port
        base) plus ``[env.workspace.vars]`` entries only.  ``WINTER_PORT_BASE``
        is deliberately NOT included for the workspace scope — the workspace band
        is exposed only as ``WINTER_WORKSPACE_PORT_BASE`` so the name carries one
        meaning everywhere.

        Band selection by scope:

        - workspace scope: ``[env.workspace.vars]`` entries only.
        - feature scope: ``[env.workspace.vars]`` rendered first, then
          ``[env.feature.vars]`` on top (feature wins key collisions; feature
          templates may reference workspace-band keys already in scope).

        Raises ``ValueError`` when a band template has an unsupported token or a
        reference to an undefined variable.
        """
        workspace_port_base = str(self._config.port_base_for_index(0))

        if scope == WORKSPACE_SCOPE:
            result: dict[str, str] = {
                "WINTER_ENV": WORKSPACE_SCOPE,
                "WINTER_ENV_INDEX": "0",
                "WINTER_WORKSPACE_PORT_BASE": workspace_port_base,
            }
        else:
            trio = build_env_trio(scope, self._config, self._registry)
            result = {**trio, "WINTER_WORKSPACE_PORT_BASE": workspace_port_base}

        bands = self._config.env_bands
        workspace_band = bands.workspace
        feature_band = bands.feature

        if workspace_band or feature_band:
            if scope == WORKSPACE_SCOPE:
                # Workspace band template scope: base vars only (no WINTER_PORT_BASE —
                # it is not in `result` for workspace scope, and we do not inject an
                # alias).  Workspace-band templates that reference ${WINTER_PORT_BASE+N}
                # raise undefined-variable ValueError, surfacing the mistake.  Use
                # ${WINTER_WORKSPACE_PORT_BASE+N} instead to target the workspace band.
                ws_template_scope = dict(result)
                _render_band("env.workspace.vars", workspace_band, ws_template_scope, result)
            else:
                # Feature scope: render the workspace band first so feature-band
                # templates may reference workspace entries.  The workspace band's
                # template scope deliberately EXCLUDES WINTER_PORT_BASE so workspace-
                # band entries resolve identically regardless of which scope they are
                # rendered in — a workspace-band template using ${WINTER_PORT_BASE+N}
                # raises undefined-variable ValueError here too.
                ws_template_scope = {k: v for k, v in result.items() if k != "WINTER_PORT_BASE"}
                _render_band("env.workspace.vars", workspace_band, ws_template_scope, result)
                # Feature band gets the full accumulated scope INCLUDING WINTER_PORT_BASE
                # and already-rendered workspace-band keys.
                feat_template_scope = dict(result)
                _render_band("env.feature.vars", feature_band, feat_template_scope, result)

        return result
