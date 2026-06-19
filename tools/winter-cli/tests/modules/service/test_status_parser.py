from __future__ import annotations

import json

import pytest

from winter_cli.modules.service.status_models import ServiceStatus, StatusDocument
from winter_cli.modules.service.status_parser import StatusDocumentParser, StatusParseError

_parser = StatusDocumentParser()

# ── helpers ───────────────────────────────────────────────────────────────────


def _raw(**kwargs: object) -> str:
    """Serialise a dict to a JSON string for use as raw_stdout."""
    return json.dumps(kwargs)


def _full_service(**overrides: object) -> dict:
    """Return a complete service dict with optional field overrides."""
    base: dict[str, object] = {
        "name": "api",
        "state": "running",
        "health": "healthy",
        "ports": [7503],
        "handle": "mp-alpha:0.1",
        "log_path": "/tmp/alpha/api.log",
        "since": "2026-06-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _full_env(**overrides: object) -> dict:
    """Return a complete env dict with optional field overrides."""
    base: dict[str, object] = {
        "env": "alpha",
        "session": "mp-alpha",
        "port_base": 4020,
        "services": [_full_service()],
    }
    base.update(overrides)
    return base


def _doc_json(*envs: dict) -> str:
    return json.dumps({"envs": list(envs)})


# ── full single-env parse — all fields ───────────────────────────────────────


def test_full_single_env_parse_all_fields() -> None:
    """A complete single-env document parses with all fields present."""
    raw = _doc_json(_full_env())
    doc = _parser.parse(raw)

    assert len(doc.envs) == 1
    env = doc.envs[0]
    assert env.env == "alpha"
    assert env.session == "mp-alpha"
    assert env.port_base == 4020
    assert len(env.services) == 1

    svc = env.services[0]
    assert svc.name == "api"
    assert svc.state == "running"
    assert svc.health == "healthy"
    assert svc.ports == (7503,)
    assert svc.handle == "mp-alpha:0.1"
    assert svc.log_path == "/tmp/alpha/api.log"
    assert svc.since == "2026-06-01T00:00:00Z"


# ── multi-env parse ───────────────────────────────────────────────────────────


def test_multi_env_parse() -> None:
    """Multiple env entries are all parsed and preserved."""
    raw = _doc_json(
        _full_env(env="alpha", session="mp-alpha", port_base=4020),
        _full_env(
            env="beta",
            session="mp-beta",
            port_base=4040,
            services=[
                _full_service(name="worker", state="stopped", health="unknown"),
            ],
        ),
    )
    doc = _parser.parse(raw)

    assert len(doc.envs) == 2
    assert doc.envs[0].env == "alpha"
    assert doc.envs[1].env == "beta"
    assert doc.envs[1].services[0].name == "worker"
    assert doc.envs[1].services[0].state == "stopped"


# ── shape-stability: missing optional fields get safe defaults ────────────────


def test_missing_health_defaults_to_unknown() -> None:
    svc = _full_service()
    del svc["health"]
    raw = _doc_json(_full_env(services=[svc]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].health == "unknown"


def test_missing_ports_defaults_to_empty_tuple() -> None:
    svc = _full_service()
    del svc["ports"]
    raw = _doc_json(_full_env(services=[svc]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].ports == ()


def test_missing_since_defaults_to_none() -> None:
    svc = _full_service()
    del svc["since"]
    raw = _doc_json(_full_env(services=[svc]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].since is None


def test_missing_handle_defaults_to_none() -> None:
    svc = _full_service()
    del svc["handle"]
    raw = _doc_json(_full_env(services=[svc]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].handle is None


def test_missing_log_path_defaults_to_none() -> None:
    svc = _full_service()
    del svc["log_path"]
    raw = _doc_json(_full_env(services=[svc]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].log_path is None


def test_missing_session_defaults_to_none() -> None:
    env = _full_env()
    del env["session"]
    raw = _doc_json(env)
    doc = _parser.parse(raw)
    assert doc.envs[0].session is None


def test_missing_port_base_defaults_to_none() -> None:
    env = _full_env()
    del env["port_base"]
    raw = _doc_json(env)
    doc = _parser.parse(raw)
    assert doc.envs[0].port_base is None


# ── unknown enum values coerced to "unknown" ──────────────────────────────────


def test_unknown_state_value_coerced_to_unknown() -> None:
    raw = _doc_json(_full_env(services=[_full_service(state="pending")]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].state == "unknown"


def test_unknown_health_value_coerced_to_unknown() -> None:
    raw = _doc_json(_full_env(services=[_full_service(health="degraded")]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].health == "unknown"


def test_non_string_state_coerced_to_unknown() -> None:
    raw = _doc_json(_full_env(services=[_full_service(state=42)]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].state == "unknown"


def test_non_string_health_coerced_to_unknown() -> None:
    raw = _doc_json(_full_env(services=[_full_service(health=True)]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].health == "unknown"


# ── ports: invalid / mixed types filtered ────────────────────────────────────


def test_non_int_port_entries_filtered_out() -> None:
    raw = _doc_json(_full_env(services=[_full_service(ports=[7503, "not-an-int", None])]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].ports == (7503,)


def test_non_list_ports_becomes_empty_tuple() -> None:
    raw = _doc_json(_full_env(services=[_full_service(ports="7503")]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].ports == ()


def test_bool_ports_filtered_out() -> None:
    """bool is a subclass of int in Python; booleans must not be accepted as port numbers."""
    raw = _doc_json(_full_env(services=[_full_service(ports=[True, False, 8080])]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].ports == (8080,)


# ── forward-compat: extra unknown fields ignored ──────────────────────────────


def test_extra_unknown_fields_in_service_ignored() -> None:
    svc = _full_service()
    svc["future_field"] = "some-value"  # type: ignore[assignment]
    raw = _doc_json(_full_env(services=[svc]))
    doc = _parser.parse(raw)
    assert doc.envs[0].services[0].name == "api"


def test_extra_unknown_fields_in_env_ignored() -> None:
    env = _full_env()
    env["future_env_field"] = 99  # type: ignore[assignment]
    raw = _doc_json(env)
    doc = _parser.parse(raw)
    assert doc.envs[0].env == "alpha"


# ── malformed JSON → StatusParseError ────────────────────────────────────────


def test_malformed_json_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError, match="valid JSON"):
        _parser.parse("not json at all {")


def test_empty_string_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError):
        _parser.parse("")


# ── top-level not a dict → StatusParseError ──────────────────────────────────


def test_top_level_list_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError, match="JSON object"):
        _parser.parse("[]")


def test_top_level_string_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError):
        _parser.parse('"just-a-string"')


def test_top_level_null_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError):
        _parser.parse("null")


# ── missing envs key → StatusParseError ──────────────────────────────────────


def test_missing_envs_key_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError, match="'envs'"):
        _parser.parse('{"other": []}')


# ── envs not a list → StatusParseError ───────────────────────────────────────


def test_envs_not_a_list_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError, match="list"):
        _parser.parse('{"envs": {}}')


def test_envs_null_raises_status_parse_error() -> None:
    with pytest.raises(StatusParseError, match="list"):
        _parser.parse('{"envs": null}')


# ── valid empty document — no error ──────────────────────────────────────────


def test_empty_envs_list_parses_cleanly_to_empty_document() -> None:
    doc = _parser.parse('{"envs": []}')
    assert isinstance(doc, StatusDocument)
    assert doc.envs == ()


# ── to_json_obj round-trip ────────────────────────────────────────────────────


def test_to_json_obj_emits_all_fields_with_ports_as_list() -> None:
    """to_json_obj must always include every field; ports must be a list."""
    doc = _parser.parse(_doc_json(_full_env()))
    obj = _parser.to_json_obj(doc)

    assert "envs" in obj
    env_obj = obj["envs"][0]
    assert set(env_obj.keys()) >= {"env", "session", "port_base", "services"}

    svc_obj = env_obj["services"][0]
    assert set(svc_obj.keys()) >= {"name", "state", "health", "ports", "handle", "log_path", "since"}
    assert isinstance(svc_obj["ports"], list)
    assert svc_obj["ports"] == [7503]


def test_to_json_obj_preserves_none_fields() -> None:
    """None values must appear as null (not absent) in the serialised output."""
    svc_dict = _full_service(handle=None, log_path=None, since=None)
    env_dict = _full_env(session=None, port_base=None, services=[svc_dict])
    doc = _parser.parse(_doc_json(env_dict))
    obj = _parser.to_json_obj(doc)

    env_obj = obj["envs"][0]
    assert env_obj["session"] is None
    assert env_obj["port_base"] is None

    svc_obj = env_obj["services"][0]
    assert svc_obj["handle"] is None
    assert svc_obj["log_path"] is None
    assert svc_obj["since"] is None


def test_to_json_obj_round_trips_through_json_serialisation() -> None:
    """The dict from to_json_obj must be JSON-serialisable and re-parseable."""
    doc = _parser.parse(_doc_json(_full_env()))
    obj = _parser.to_json_obj(doc)
    serialised = json.dumps(obj)
    reparsed = _parser.parse(serialised)
    assert reparsed.envs[0].env == "alpha"
    assert reparsed.envs[0].services[0].ports == (7503,)


def test_to_json_obj_key_order_matches_schema() -> None:
    """Keys appear in the documented schema order."""
    doc = _parser.parse(_doc_json(_full_env()))
    obj = _parser.to_json_obj(doc)

    env_keys = list(obj["envs"][0].keys())
    assert env_keys == ["env", "session", "port_base", "services"]

    svc_keys = list(obj["envs"][0]["services"][0].keys())
    assert svc_keys == ["name", "state", "health", "ports", "handle", "log_path", "since"]


def test_to_json_obj_empty_document() -> None:
    """to_json_obj on an empty document returns a dict with an empty envs list."""
    doc = _parser.parse('{"envs": []}')
    obj = _parser.to_json_obj(doc)
    assert obj == {"envs": []}


# ── dataclass frozenness ──────────────────────────────────────────────────────


def test_service_status_is_frozen() -> None:
    svc = ServiceStatus(
        name="api",
        state="running",
        health="healthy",
        ports=(8080,),
        handle=None,
        log_path=None,
        since=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        svc.name = "other"  # type: ignore[misc]


def test_status_document_is_frozen() -> None:
    doc = StatusDocument(envs=())
    with pytest.raises((AttributeError, TypeError)):
        doc.envs = ()  # type: ignore[misc]
