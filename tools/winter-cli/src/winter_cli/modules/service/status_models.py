"""Typed data models for the winter service status document.

Parsing and serialisation live in ``status_parser.py`` (``StatusDocumentParser``).
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class ServiceStatus:
    """Status of a single service within an env."""

    name: str
    state: str
    health: str
    ports: tuple[int, ...]
    handle: str | None
    log_path: str | None
    since: str | None


@dataclasses.dataclass(frozen=True)
class EnvStatus:
    """Status of one feature environment."""

    env: str
    session: str | None
    port_base: int | None
    services: tuple[ServiceStatus, ...]


@dataclasses.dataclass(frozen=True)
class StatusDocument:
    """Top-level status document covering one or more environments."""

    envs: tuple[EnvStatus, ...]


@dataclasses.dataclass(frozen=True)
class StatusOptions:
    """Parsed options for ``winter service status``.

    ``patterns`` is a tuple of zero or more ``<env>/<service>`` segment-glob
    strings used to filter the parsed document before rendering.
    ``as_json`` selects JSON output instead of the human table.
    """

    patterns: tuple[str, ...]
    as_json: bool
