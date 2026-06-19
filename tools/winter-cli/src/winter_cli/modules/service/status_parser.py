"""Parser and serialiser for the winter service status document.

The orchestrator emits a JSON object on stdout for the `status` action.  Winter
parses that object into frozen dataclasses (shape-stability: missing / invalid
fields receive safe defaults) and re-serialises the canonical form for ``--json``
output.  Rendering (table or JSON) is winter's responsibility; the orchestrator
argv is byte-identical whether or not ``--json`` is set.

Schema (env-keyed)::

    {
      "envs": [
        {
          "env": "alpha",
          "session": "mp-alpha" | null,
          "port_base": 4020 | null,
          "services": [
            {
              "name": "api",
              "state": "running" | "stopped" | "unknown",
              "health": "healthy" | "unhealthy" | "unknown",
              "ports": [7503],
              "handle": "<str>" | null,
              "log_path": "/abs/path" | null,
              "since": "<RFC3339>" | null
            }
          ]
        }
      ]
    }
"""

from __future__ import annotations

import json
from typing import Any

from winter_cli.modules.service.status_models import EnvStatus, ServiceStatus, StatusDocument


class StatusParseError(Exception):
    """Raised when the orchestrator output cannot be parsed as a status document.

    The message is human-readable and actionable — it names the specific
    non-conformance so the operator knows whether to look at the orchestrator
    or at winter itself.
    """


_VALID_STATES = frozenset({"running", "stopped", "unknown"})
_VALID_HEALTH = frozenset({"healthy", "unhealthy", "unknown"})


def _coerce_str_or_none(value: object) -> str | None:
    """Return a str if value is a str, else None."""
    return value if isinstance(value, str) else None


def _coerce_int_or_none(value: object) -> int | None:
    """Return an int if value is an int (and not bool), else None."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _coerce_ports(value: object) -> tuple[int, ...]:
    """Coerce a raw value to a tuple of ints; non-list or non-int elements dropped."""
    if not isinstance(value, list):
        return ()
    return tuple(v for v in value if isinstance(v, int) and not isinstance(v, bool))


def _parse_service(raw: object) -> ServiceStatus:
    """Parse one service entry from a raw (possibly non-dict) value."""
    if not isinstance(raw, dict):
        raw = {}

    name = str(raw.get("name", "")) if isinstance(raw.get("name"), str) else ""

    raw_state = raw.get("state")
    state = raw_state if isinstance(raw_state, str) and raw_state in _VALID_STATES else "unknown"

    raw_health = raw.get("health")
    health = raw_health if isinstance(raw_health, str) and raw_health in _VALID_HEALTH else "unknown"

    ports = _coerce_ports(raw.get("ports"))
    handle = _coerce_str_or_none(raw.get("handle"))
    log_path = _coerce_str_or_none(raw.get("log_path"))
    since = _coerce_str_or_none(raw.get("since"))

    return ServiceStatus(
        name=name,
        state=state,
        health=health,
        ports=ports,
        handle=handle,
        log_path=log_path,
        since=since,
    )


def _parse_env(raw: object) -> EnvStatus:
    """Parse one env entry from a raw (possibly non-dict) value."""
    if not isinstance(raw, dict):
        raw = {}

    env = str(raw.get("env", "")) if isinstance(raw.get("env"), str) else ""
    session = _coerce_str_or_none(raw.get("session"))
    port_base = _coerce_int_or_none(raw.get("port_base"))

    raw_services = raw.get("services")
    services_list: list[object] = raw_services if isinstance(raw_services, list) else []
    services = tuple(_parse_service(s) for s in services_list)

    return EnvStatus(env=env, session=session, port_base=port_base, services=services)


class StatusDocumentParser:
    """Owns parsing the orchestrator status document and serialising it back to canonical JSON."""

    def parse(self, raw_stdout: str) -> StatusDocument:
        """Parse the orchestrator's stdout into a typed ``StatusDocument``.

        Applies shape-stability defaults so callers can always rely on every field
        being present.  An empty ``{"envs": []}`` is a valid, non-error document.

        Raises ``StatusParseError`` on hard non-conformance: malformed JSON, a
        top-level value that is not a dict, or a missing / non-list ``envs`` key.
        """
        try:
            obj = json.loads(raw_stdout)
        except json.JSONDecodeError as exc:
            raise StatusParseError(f"orchestrator did not emit a valid JSON status document: {exc}") from exc

        if not isinstance(obj, dict):
            raise StatusParseError(
                f"orchestrator status document must be a JSON object at the top level, got {type(obj).__name__}"
            )

        if "envs" not in obj:
            raise StatusParseError("orchestrator status document is missing the required 'envs' key")

        raw_envs = obj["envs"]
        if not isinstance(raw_envs, list):
            raise StatusParseError(f"orchestrator status document 'envs' must be a list, got {type(raw_envs).__name__}")

        envs = tuple(_parse_env(e) for e in raw_envs)
        return StatusDocument(envs=envs)

    def to_json_obj(self, doc: StatusDocument) -> dict[str, Any]:
        """Rebuild the canonical, schema-ordered dict from a ``StatusDocument``.

        Every field is always present; ``ports`` is a list; enum values and ``None``
        are preserved as-is.  Key order matches the schema definition.
        """
        return {
            "envs": [
                {
                    "env": env.env,
                    "session": env.session,
                    "port_base": env.port_base,
                    "services": [
                        {
                            "name": svc.name,
                            "state": svc.state,
                            "health": svc.health,
                            "ports": list(svc.ports),
                            "handle": svc.handle,
                            "log_path": svc.log_path,
                            "since": svc.since,
                        }
                        for svc in env.services
                    ],
                }
                for env in doc.envs
            ]
        }
