"""Extension-declared service definitions and workspace aggregation.

An extension declares bare services in its ``winter-ext.toml`` under a
``[[service]]`` array.  Winter-CLI aggregates these across the workspace manifest
and every installed extension, checks for name collisions, and writes the merged
list to a temporary TOML file whose path is handed to each orchestrator provider
via the ``WINTER_SERVICE_MANIFEST`` environment variable.

Contract
--------
- ``ExtServiceDef`` is an immutable value object carrying the fields an
  extension may declare about a service (``name``, ``command``/``image``,
  ``scope``, ``ports``).  Unknown keys REJECT at parse time (mirrors
  ``ProvisionManifestParser`` strictness).
- ``ExtServiceManifestParser`` parses the raw ``[[service]]`` list from a
  single ``winter-ext.toml`` with full unknown-key rejection.
- ``ServiceDefinitionAggregator`` collects defs from:
  1. The workspace config (``service_defs_raw`` field) — source label
     ``"workspace"``.
  2. Every installed extension manifest — source label is the extension prefix.
  Ordering: workspace defs first, then extensions in declaration order.
  Colliding names across sources produce a ``ConfigError`` naming both sources.
- ``write_service_manifest_toml`` serialises the aggregated list to a TOML
  file so providers can read it without knowing the aggregation logic.

Orchestrator contract
---------------------
When an aggregated manifest is available, ``build_provider_env`` callers
inject it as ``WINTER_SERVICE_MANIFEST=<absolute_path>``.  Providers may
consume or ignore it.  A provider that does not read the file simply starts
only the services declared in its own ``config.toml``.

This module is a cold-path import (only loaded during ``service up/down``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from winter_cli.core.config_file import ConfigError

logger = logging.getLogger(__name__)

# ── Allowed keys in a [[service]] entry ─────────────────────────────────────

_ENTRY_ALLOWED_KEYS = frozenset({"name", "command", "image", "scope", "ports", "target"})

# Valid scope values (mirrors the catalog scope names).
_VALID_SCOPES = frozenset({"workspace", "feature-environment"})


# ── ExtServiceDef ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExtServiceDef:
    """A single service declared by an extension or the workspace config.

    Fields:
        name:    Unique service identifier (required).
        scope:   ``"workspace"`` or ``"feature-environment"`` (default).
        command: Shell command string (optional — provider may default).
        image:   Container image reference (optional — used by docker provider).
        target:  Provider-specific placement hint (optional).  For the tmux
                 provider this is a ``"<window>.<pane>"`` string.  Ignored by
                 providers that do not understand it.
        ports:   Ordered list of port labels declared for this service (optional).
        source:  The label identifying the declaring source (extension prefix or
                 ``"workspace"``).  Set by the aggregator, not by the parser.
    """

    name: str
    scope: str
    source: str
    command: str = ""
    image: str = ""
    target: str = ""
    ports: tuple[str, ...] = field(default_factory=tuple)


# ── ExtServiceManifestParser ─────────────────────────────────────────────────


class ExtServiceManifestParser:
    """Parses the raw ``[[service]]`` list from a single manifest source.

    Raises ``ConfigError`` on any structural or semantic violation, including
    unknown keys (strict — mirrors ``ProvisionManifestParser``).

    ``source`` is the human-readable label used in error messages and stored on
    each ``ExtServiceDef`` (e.g. the extension prefix or ``"workspace"``).
    """

    def parse(self, raw: object, source: str) -> list[ExtServiceDef]:
        """Parse a raw ``[[service]]`` value into a list of ``ExtServiceDef``.

        ``raw`` is the value of the ``service`` key in the TOML document — a
        list of dicts.  Returns ``[]`` for ``None`` or non-list input.
        """
        if not raw:
            return []

        if not isinstance(raw, list):
            raise ConfigError(f"[[service]] in {source!r} must be an array of tables, got {type(raw).__name__!r}.")

        defs: list[ExtServiceDef] = []

        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ConfigError(
                    f"[[service]][{i}] in {source!r} must be a table (dict), got {type(entry).__name__!r}."
                )

            unknown = set(entry.keys()) - _ENTRY_ALLOWED_KEYS
            if unknown:
                bad = ", ".join(repr(k) for k in sorted(unknown))
                allowed = ", ".join(repr(k) for k in sorted(_ENTRY_ALLOWED_KEYS))
                raise ConfigError(f"Unknown key(s) {bad} in [[service]][{i}] in {source!r}. Allowed keys: {allowed}.")

            name_raw = entry.get("name")
            if not name_raw or not isinstance(name_raw, str):
                raise ConfigError(
                    f"[[service]][{i}] in {source!r} is missing required field 'name' (must be a non-empty string)."
                )

            scope_raw = entry.get("scope", "feature-environment")
            if not isinstance(scope_raw, str) or scope_raw not in _VALID_SCOPES:
                valid = ", ".join(repr(s) for s in sorted(_VALID_SCOPES))
                raise ConfigError(
                    f"Invalid scope {scope_raw!r} in [[service]][{i}] in {source!r}. Must be one of: {valid}."
                )

            command_raw = entry.get("command", "")
            if not isinstance(command_raw, str):
                raise ConfigError(
                    f"[[service]][{i}].command in {source!r} must be a string, got {type(command_raw).__name__!r}."
                )

            image_raw = entry.get("image", "")
            if not isinstance(image_raw, str):
                raise ConfigError(
                    f"[[service]][{i}].image in {source!r} must be a string, got {type(image_raw).__name__!r}."
                )

            target_raw = entry.get("target", "")
            if not isinstance(target_raw, str):
                raise ConfigError(
                    f"[[service]][{i}].target in {source!r} must be a string, got {type(target_raw).__name__!r}."
                )

            ports_raw = entry.get("ports", [])
            if not isinstance(ports_raw, list) or not all(isinstance(p, str) for p in ports_raw):
                raise ConfigError(f"[[service]][{i}].ports in {source!r} must be a list of strings.")

            defs.append(
                ExtServiceDef(
                    name=name_raw,
                    scope=scope_raw,
                    source=source,
                    command=command_raw,
                    image=image_raw,
                    target=target_raw,
                    ports=tuple(ports_raw),
                )
            )

        return defs


# ── ServiceDefinitionAggregator ──────────────────────────────────────────────


@dataclass(frozen=True)
class AggregatedServiceDefs:
    """The ordered, collision-free aggregate of service definitions.

    ``defs`` is the fully ordered list: workspace defs first, then extension
    defs in extension-declaration order.
    """

    defs: tuple[ExtServiceDef, ...]


class ServiceDefinitionAggregator:
    """Collects service definitions from the workspace config and all extensions.

    Ordering (mirrors provision aggregation):
    1. Workspace-config defs (source ``"workspace"``) first.
    2. Extension defs in the order extensions are declared in the workspace config.

    Collision detection: two sources declaring the same service ``name`` produce a
    ``ConfigError`` naming both sources.  Silent override is never permitted.
    """

    def aggregate(
        self,
        workspace_defs: list[ExtServiceDef],
        extension_def_groups: list[list[ExtServiceDef]],
    ) -> AggregatedServiceDefs:
        """Aggregate workspace + extension definitions.

        ``workspace_defs`` are the defs from the workspace-level ``[[service]]``
        block (source label ``"workspace"``).
        ``extension_def_groups`` is a list of per-extension def lists, in the
        order extensions should contribute.
        """
        seen: dict[str, str] = {}  # name → source that first declared it
        ordered: list[ExtServiceDef] = []

        for svc in workspace_defs:
            if svc.name in seen:
                raise ConfigError(
                    f"Service name {svc.name!r} is declared by both "
                    f"{seen[svc.name]!r} and {svc.source!r}. "
                    f"Service names must be unique across all sources."
                )
            seen[svc.name] = svc.source
            ordered.append(svc)

        for group in extension_def_groups:
            for svc in group:
                if svc.name in seen:
                    raise ConfigError(
                        f"Service name {svc.name!r} is declared by both "
                        f"{seen[svc.name]!r} and {svc.source!r}. "
                        f"Service names must be unique across all sources."
                    )
                seen[svc.name] = svc.source
                ordered.append(svc)

        return AggregatedServiceDefs(defs=tuple(ordered))


# ── TOML serialisation ────────────────────────────────────────────────────────


def write_service_manifest_toml(defs: tuple[ExtServiceDef, ...], path: Path) -> None:
    """Write a minimal TOML file containing the aggregated service definitions.

    The file format is a list of ``[[service]]`` tables consumable by any
    provider that understands the ``WINTER_SERVICE_MANIFEST`` contract::

        [[service]]
        name    = "my-service"
        scope   = "feature-environment"
        source  = "my-ext"
        command = "..."
        image   = ""
        ports   = []

    Providers read this file to discover extension-declared services and merge
    them into their running configuration.
    """
    lines: list[str] = []
    for svc in defs:
        lines.append("[[service]]")
        lines.append(f"name    = {svc.name!r}")
        lines.append(f"scope   = {svc.scope!r}")
        lines.append(f"source  = {svc.source!r}")
        if svc.command:
            lines.append(f"command = {svc.command!r}")
        if svc.image:
            lines.append(f"image   = {svc.image!r}")
        if svc.target:
            lines.append(f"target  = {svc.target!r}")
        if svc.ports:
            ports_toml = "[" + ", ".join(repr(p) for p in svc.ports) + "]"
            lines.append(f"ports   = {ports_toml}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
