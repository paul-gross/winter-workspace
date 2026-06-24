"""Tests for ServiceManifestCollectorService.

Covers:
- No extension defs → CollectedManifest.has_defs is False, no file written
- Extension-only defs → file written, env_additions has WINTER_SERVICE_MANIFEST
- Workspace + extension merge → defs ordered workspace-first
- Name collision across sources → click.ClickException with dual-source message
- Malformed extension manifest → warning logged, extension skipped
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeConfigFileReader
from winter_cli.modules.service.service_manifest_collector import (
    WINTER_SERVICE_MANIFEST_ENV,
    ServiceManifestCollectorService,
)
from winter_cli.modules.workspace.extension_manifest import ExtensionManifestLoader
from winter_cli.modules.workspace.models import StandaloneRepository

WORKSPACE_ROOT = Path("/ws")


# ── Fakes / stubs ─────────────────────────────────────────────────────────────


class FakeFilesystemReader:
    """Minimal IFilesystemReader backed by a set of existing paths."""

    def __init__(self, existing: set[Path] | None = None) -> None:
        self._existing: set[Path] = existing or set()

    def exists(self, path: Path) -> bool:
        return path in self._existing

    def is_file(self, path: Path) -> bool:
        return path in self._existing

    def is_dir(self, path: Path) -> bool:
        return False

    def is_symlink(self, path: Path) -> bool:
        return False

    def iterdir(self, path: Path) -> list[Path]:
        return []

    def read_text(self, path: Path) -> str:
        raise FileNotFoundError(path)

    def read_bytes(self, path: Path) -> bytes:
        raise FileNotFoundError(path)

    def readlink(self, path: Path) -> Path:
        raise FileNotFoundError(path)

    def access_x_ok(self, path: Path) -> bool:
        return False


class FakeRepoFactory:
    """Returns a fixed list of StandaloneRepository objects."""

    def __init__(self, repos: list[StandaloneRepository]) -> None:
        self._repos = repos

    def get_standalone_repos(self) -> list[StandaloneRepository]:
        return list(self._repos)


def _make_repo(name: str) -> StandaloneRepository:
    return StandaloneRepository(name=name, path=WORKSPACE_ROOT / name)


def _make_svc(
    workspace_root: Path = WORKSPACE_ROOT,
    workspace_raw: list | None = None,
    config_files: dict | None = None,
    repos: list[StandaloneRepository] | None = None,
) -> ServiceManifestCollectorService:
    """Build a ServiceManifestCollectorService with fakes."""
    workspace_raw = workspace_raw or []
    repos = repos or []
    config_files = config_files or {}

    # Existing paths are all keys in config_files.
    existing = set(config_files.keys())

    manifest_loader = ExtensionManifestLoader(
        config_file_reader=FakeConfigFileReader(config_files),
    )
    repo_factory = FakeRepoFactory(repos)
    fs = FakeFilesystemReader(existing)

    return ServiceManifestCollectorService(
        workspace_root=workspace_root,
        workspace_service_defs_raw=workspace_raw,
        manifest_loader=manifest_loader,
        repo_factory=repo_factory,
        fs=fs,
    )


# ── no-defs case ──────────────────────────────────────────────────────────────


def test_collect_no_defs_returns_no_manifest_path() -> None:
    """When no service defs are declared anywhere, no TOML file is written."""
    svc = _make_svc()
    result = svc.collect()
    assert not result.has_defs
    assert result.manifest_path is None
    assert result.env_additions() == {}


def test_collect_no_defs_aggregated_is_empty() -> None:
    svc = _make_svc()
    result = svc.collect()
    assert result.aggregated.defs == ()


# ── extension-only defs ───────────────────────────────────────────────────────


def test_collect_extension_only_defs(tmp_path: Path) -> None:
    """Extension-only defs: manifest path is set, env_additions has the key."""
    repo = _make_repo("my-ext")
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "my-ext",
            "service": [{"name": "api", "scope": "feature-environment"}],
        }
    }
    svc = _make_svc(repos=[repo], config_files=config_files)
    result = svc.collect()
    assert result.has_defs
    assert result.manifest_path is not None
    assert result.manifest_path.exists()
    additions = result.env_additions()
    assert WINTER_SERVICE_MANIFEST_ENV in additions
    assert additions[WINTER_SERVICE_MANIFEST_ENV] == str(result.manifest_path)


def test_collect_extension_only_def_names(tmp_path: Path) -> None:
    repo = _make_repo("my-ext")
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "my-ext",
            "service": [
                {"name": "api", "scope": "feature-environment"},
                {"name": "worker", "scope": "feature-environment"},
            ],
        }
    }
    svc = _make_svc(repos=[repo], config_files=config_files)
    result = svc.collect()
    assert [d.name for d in result.aggregated.defs] == ["api", "worker"]
    assert all(d.source == "my-ext" for d in result.aggregated.defs)


# ── workspace + extension merge ───────────────────────────────────────────────


def test_collect_workspace_plus_extension_order() -> None:
    """Workspace defs appear before extension defs."""
    repo = _make_repo("my-ext")
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "my-ext",
            "service": [{"name": "worker"}],
        }
    }
    workspace_raw = [{"name": "postgres", "scope": "workspace"}]
    svc = _make_svc(workspace_raw=workspace_raw, repos=[repo], config_files=config_files)
    result = svc.collect()
    names = [d.name for d in result.aggregated.defs]
    assert names == ["postgres", "worker"]
    assert result.aggregated.defs[0].source == "workspace"
    assert result.aggregated.defs[1].source == "my-ext"


# ── name collision ────────────────────────────────────────────────────────────


def test_collect_name_collision_raises_with_both_sources() -> None:
    """Colliding service names across sources → ClickException naming both sources."""
    import click

    repo = _make_repo("my-ext")
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "my-ext",
            "service": [{"name": "api"}],
        }
    }
    workspace_raw = [{"name": "api", "scope": "feature-environment"}]
    svc = _make_svc(workspace_raw=workspace_raw, repos=[repo], config_files=config_files)
    with pytest.raises(click.ClickException) as exc_info:
        svc.collect()
    msg = str(exc_info.value.format_message())
    assert "api" in msg
    assert "workspace" in msg
    assert "my-ext" in msg


# ── malformed extension manifest — graceful skip ──────────────────────────────


def test_collect_malformed_extension_manifest_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """A malformed [[service]] entry in an extension is skipped with a warning."""
    import logging

    repo = _make_repo("bad-ext")
    manifest_path = WORKSPACE_ROOT / "bad-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "bad-ext",
            "service": [{"name": "svc", "unknown_key": "bad"}],
        }
    }
    svc = _make_svc(repos=[repo], config_files=config_files)
    with caplog.at_level(logging.WARNING):
        result = svc.collect()

    # The bad extension is skipped, no defs collected.
    assert not result.has_defs
    assert any("bad-ext" in r.message for r in caplog.records)


# ── scope routing ─────────────────────────────────────────────────────────────


def test_collect_workspace_scope_preserved() -> None:
    """A service declared with scope=workspace keeps that scope in the aggregate."""
    repo = _make_repo("ext")
    manifest_path = WORKSPACE_ROOT / "ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "ext",
            "service": [{"name": "db", "scope": "workspace"}],
        }
    }
    svc = _make_svc(repos=[repo], config_files=config_files)
    result = svc.collect()
    assert result.aggregated.defs[0].scope == "workspace"


def test_collect_feature_env_scope_preserved() -> None:
    """A service declared with scope=feature-environment keeps that scope."""
    repo = _make_repo("ext")
    manifest_path = WORKSPACE_ROOT / "ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "ext",
            "service": [{"name": "api", "scope": "feature-environment"}],
        }
    }
    svc = _make_svc(repos=[repo], config_files=config_files)
    result = svc.collect()
    assert result.aggregated.defs[0].scope == "feature-environment"
