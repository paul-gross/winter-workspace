"""Tests for ExtServiceManifestParser and ServiceDefinitionAggregator.

Covers:
- ExtServiceManifestParser: valid parse, missing name, unknown keys, invalid scope,
  non-string fields
- ServiceDefinitionAggregator: extension-only, workspace+extension merge, name
  collision across sources, scope routing (workspace vs feature-environment)
- write_service_manifest_toml: produces parseable TOML with expected content
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from winter_cli.core.config_file import ConfigError
from winter_cli.modules.service.ext_service_manifest import (
    AggregatedServiceDefs,
    ExtServiceDef,
    ExtServiceManifestParser,
    ServiceDefinitionAggregator,
    write_service_manifest_toml,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse(raw: object, source: str = "test-ext") -> list[ExtServiceDef]:
    return ExtServiceManifestParser().parse(raw, source)


def _aggregate(
    workspace: list[ExtServiceDef],
    ext_groups: list[list[ExtServiceDef]],
) -> AggregatedServiceDefs:
    return ServiceDefinitionAggregator().aggregate(workspace, ext_groups)


def _def(name: str, scope: str = "feature-environment", source: str = "test-ext") -> ExtServiceDef:
    return ExtServiceDef(name=name, scope=scope, source=source)


# ── ExtServiceManifestParser — valid cases ────────────────────────────────────


def test_parse_none_returns_empty() -> None:
    assert _parse(None) == []


def test_parse_empty_list_returns_empty() -> None:
    assert _parse([]) == []


def test_parse_minimal_entry() -> None:
    """A bare [[service]] with just a name is valid (scope defaults to feature-env)."""
    result = _parse([{"name": "my-svc"}], source="my-ext")
    assert len(result) == 1
    svc = result[0]
    assert svc.name == "my-svc"
    assert svc.scope == "feature-environment"
    assert svc.source == "my-ext"
    assert svc.command == ""
    assert svc.image == ""
    assert svc.target == ""
    assert svc.ports == ()


def test_parse_full_entry() -> None:
    """All optional fields are parsed correctly."""
    raw = [
        {
            "name": "api",
            "scope": "workspace",
            "command": "uvicorn app:app",
            "image": "my-image:latest",
            "target": "2.0",
            "ports": ["http", "grpc"],
        }
    ]
    result = _parse(raw, source="my-ext")
    assert len(result) == 1
    svc = result[0]
    assert svc.name == "api"
    assert svc.scope == "workspace"
    assert svc.command == "uvicorn app:app"
    assert svc.image == "my-image:latest"
    assert svc.target == "2.0"
    assert svc.ports == ("http", "grpc")


def test_parse_multiple_entries() -> None:
    raw = [{"name": "a"}, {"name": "b", "scope": "workspace"}]
    result = _parse(raw)
    assert [s.name for s in result] == ["a", "b"]
    assert result[0].scope == "feature-environment"
    assert result[1].scope == "workspace"


# ── ExtServiceManifestParser — error cases ────────────────────────────────────


def test_parse_non_list_input_raises() -> None:
    with pytest.raises(ConfigError, match="array of tables"):
        _parse({"name": "bad"})


def test_parse_non_dict_entry_raises() -> None:
    with pytest.raises(ConfigError, match="must be a table"):
        _parse(["not-a-dict"])


def test_parse_unknown_key_raises() -> None:
    """Unknown keys REJECT — strict like ProvisionManifestParser."""
    with pytest.raises(ConfigError, match="Unknown key"):
        _parse([{"name": "svc", "foo": "bar"}])


def test_parse_unknown_key_error_names_allowed_keys() -> None:
    with pytest.raises(ConfigError, match="Allowed keys"):
        _parse([{"name": "svc", "bad": "val"}])


def test_parse_missing_name_raises() -> None:
    with pytest.raises(ConfigError, match="missing required field 'name'"):
        _parse([{"scope": "workspace"}])


def test_parse_empty_name_raises() -> None:
    with pytest.raises(ConfigError, match="missing required field 'name'"):
        _parse([{"name": ""}])


def test_parse_invalid_scope_raises() -> None:
    with pytest.raises(ConfigError, match="Invalid scope"):
        _parse([{"name": "svc", "scope": "bad-scope"}])


def test_parse_non_string_command_raises() -> None:
    with pytest.raises(ConfigError, match="command"):
        _parse([{"name": "svc", "command": 42}])


def test_parse_non_string_target_raises() -> None:
    with pytest.raises(ConfigError, match="target"):
        _parse([{"name": "svc", "target": 1}])


def test_parse_non_list_ports_raises() -> None:
    with pytest.raises(ConfigError, match="ports"):
        _parse([{"name": "svc", "ports": "http"}])


def test_parse_ports_with_non_string_entry_raises() -> None:
    with pytest.raises(ConfigError, match="ports"):
        _parse([{"name": "svc", "ports": ["http", 8080]}])


# ── ServiceDefinitionAggregator ───────────────────────────────────────────────


def test_aggregate_empty_yields_empty() -> None:
    result = _aggregate([], [])
    assert result.defs == ()


def test_aggregate_extension_only() -> None:
    """A single extension-only service definition aggregates correctly."""
    ext_svc = _def("api", source="my-ext")
    result = _aggregate([], [[ext_svc]])
    assert len(result.defs) == 1
    assert result.defs[0].name == "api"
    assert result.defs[0].source == "my-ext"


def test_aggregate_workspace_plus_extension_merge() -> None:
    """Workspace defs come first, then extension defs in declaration order."""
    ws_svc = _def("postgres", scope="workspace", source="workspace")
    ext_svc1 = _def("api", source="ext-a")
    ext_svc2 = _def("worker", source="ext-b")
    result = _aggregate([ws_svc], [[ext_svc1], [ext_svc2]])
    names = [d.name for d in result.defs]
    # Workspace defs first, then extensions in order.
    assert names == ["postgres", "api", "worker"]


def test_aggregate_workspace_def_first() -> None:
    """Workspace defs always precede extension defs regardless of scope."""
    ws = _def("ws-svc", scope="feature-environment", source="workspace")
    ext = _def("ext-svc", source="my-ext")
    result = _aggregate([ws], [[ext]])
    assert result.defs[0].source == "workspace"
    assert result.defs[1].source == "my-ext"


def test_aggregate_extension_declaration_order_preserved() -> None:
    """Extensions contribute their defs in the order extensions appear."""
    a = _def("svc-a", source="ext-a")
    b = _def("svc-b", source="ext-b")
    c = _def("svc-c", source="ext-c")
    result = _aggregate([], [[a], [b], [c]])
    assert [d.name for d in result.defs] == ["svc-a", "svc-b", "svc-c"]


def test_aggregate_collision_workspace_and_extension_raises() -> None:
    """Name collision between workspace and extension → clear error naming both sources."""
    ws = _def("api", source="workspace")
    ext = _def("api", source="my-ext")
    with pytest.raises(ConfigError, match="api") as exc_info:
        _aggregate([ws], [[ext]])
    msg = str(exc_info.value)
    assert "workspace" in msg
    assert "my-ext" in msg


def test_aggregate_collision_two_extensions_raises() -> None:
    """Name collision between two extensions → clear error naming both."""
    a = _def("worker", source="ext-a")
    b = _def("worker", source="ext-b")
    with pytest.raises(ConfigError, match="worker") as exc_info:
        _aggregate([], [[a], [b]])
    msg = str(exc_info.value)
    assert "ext-a" in msg
    assert "ext-b" in msg


def test_aggregate_scope_routing_workspace_vs_feature_env() -> None:
    """Defs with different scopes are preserved without collapsing."""
    ws = _def("db", scope="workspace", source="workspace")
    fe = _def("api", scope="feature-environment", source="my-ext")
    result = _aggregate([ws], [[fe]])
    scopes = {d.name: d.scope for d in result.defs}
    assert scopes["db"] == "workspace"
    assert scopes["api"] == "feature-environment"


# ── write_service_manifest_toml ───────────────────────────────────────────────


def test_write_toml_produces_parseable_output(tmp_path: Path) -> None:
    """The written TOML can be round-tripped back to a dict."""
    defs = (
        ExtServiceDef(name="api", scope="feature-environment", source="my-ext", command="uvicorn app:app"),
        ExtServiceDef(name="db", scope="workspace", source="workspace"),
    )
    out = tmp_path / "manifest.toml"
    write_service_manifest_toml(defs, out)
    doc = tomllib.loads(out.read_text(encoding="utf-8"))
    services = doc["service"]
    assert len(services) == 2
    assert services[0]["name"] == "api"
    assert services[0]["scope"] == "feature-environment"
    assert services[0]["source"] == "my-ext"
    assert services[1]["name"] == "db"
    assert services[1]["scope"] == "workspace"


def test_write_toml_includes_target_when_set(tmp_path: Path) -> None:
    defs = (ExtServiceDef(name="svc", scope="feature-environment", source="ext", target="2.0"),)
    out = tmp_path / "manifest.toml"
    write_service_manifest_toml(defs, out)
    doc = tomllib.loads(out.read_text(encoding="utf-8"))
    assert doc["service"][0]["target"] == "2.0"


def test_write_toml_omits_empty_optional_fields(tmp_path: Path) -> None:
    """Empty command, image, target, and ports are omitted from the TOML output."""
    defs = (ExtServiceDef(name="bare", scope="feature-environment", source="ext"),)
    out = tmp_path / "manifest.toml"
    write_service_manifest_toml(defs, out)
    doc = tomllib.loads(out.read_text(encoding="utf-8"))
    entry = doc["service"][0]
    assert "command" not in entry
    assert "image" not in entry
    assert "target" not in entry
    assert "ports" not in entry
