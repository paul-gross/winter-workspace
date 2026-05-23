from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests.conftest import FakeConfigFileReader, FakeFilesystem
from winter_cli.modules.workspace.models import StandaloneRepository, Workspace
from winter_cli.plugins.loader import PluginRegistry
from winter_cli.plugins.types import PluginRegistration

WORKSPACE_ROOT = Path("/ws")


class FakePluginLoader:
    """IPluginLoader fake — returns canned modules keyed by entry-point path.

    Tests register `(path, module)` to control what `_load_plugin` sees.
    Modules must expose `create_plugin()` to be installed.
    """

    def __init__(self, modules: dict[Path, ModuleType]) -> None:
        self._modules = modules
        self.load_calls: list[tuple[str, Path]] = []

    def load(self, name: str, entry_point: Path) -> ModuleType:
        self.load_calls.append((name, entry_point))
        if entry_point not in self._modules:
            raise ImportError(f"unknown entry point: {entry_point}")
        return self._modules[entry_point]


def _make_module(name: str, *, config_received: list[dict]) -> ModuleType:
    """Build a fake plugin module that records the config it was registered with."""
    module = ModuleType(name)

    def create_plugin() -> SimpleNamespace:
        def register(config: object) -> PluginRegistration:
            assert isinstance(config, dict)
            config_received.append(config)
            return PluginRegistration()

        return SimpleNamespace(name=name, register=register)

    module.create_plugin = create_plugin  # type: ignore[attr-defined]
    return module


@pytest.fixture
def workspace() -> Workspace:
    return Workspace(root_path=WORKSPACE_ROOT, session_prefix="t", main_branch="main")


def test_discover_loads_workspace_local_plugin(workspace: Workspace) -> None:
    plugin_dir = WORKSPACE_ROOT / ".winter" / "plugins" / "demo"
    plugin_py = plugin_dir / "plugin.py"
    fs = FakeFilesystem(
        directories=[WORKSPACE_ROOT / ".winter" / "plugins", plugin_dir],
        files={plugin_py: ""},
    )
    config_received: list[dict] = []
    loader = FakePluginLoader({plugin_py: _make_module("demo", config_received=config_received)})

    registry = PluginRegistry(fs, FakeConfigFileReader({}), loader).discover(workspace, standalone_repos=[])

    assert [p.name for p in registry.plugins] == ["demo"]
    assert loader.load_calls == [("demo", plugin_py)]
    assert config_received == [{}]  # no config.toml present → empty dict


def test_discover_reads_plugin_config_when_present(workspace: Workspace) -> None:
    plugin_dir = WORKSPACE_ROOT / ".winter" / "plugins" / "demo"
    plugin_py = plugin_dir / "plugin.py"
    config_toml = plugin_dir / "config.toml"
    fs = FakeFilesystem(
        directories=[WORKSPACE_ROOT / ".winter" / "plugins", plugin_dir],
        files={plugin_py: "", config_toml: ""},
    )
    config_received: list[dict] = []
    loader = FakePluginLoader({plugin_py: _make_module("demo", config_received=config_received)})
    reader = FakeConfigFileReader({config_toml: {"opt_in": True, "name": "demo"}})

    PluginRegistry(fs, reader, loader).discover(workspace, standalone_repos=[])

    assert config_received == [{"opt_in": True, "name": "demo"}]


def test_discover_skips_extension_plugin_when_workspace_plugin_wins(workspace: Workspace) -> None:
    """Workspace plugin shadows a same-named plugin shipped by an extension."""
    ws_dir = WORKSPACE_ROOT / ".winter" / "plugins" / "demo"
    ws_plugin = ws_dir / "plugin.py"
    ext_path = WORKSPACE_ROOT / "ext-demo"
    ext_plugin = ext_path / "plugin.py"
    fs = FakeFilesystem(
        directories=[WORKSPACE_ROOT / ".winter" / "plugins", ws_dir, ext_path],
        files={ws_plugin: "", ext_plugin: ""},
    )
    config_received: list[dict] = []
    loader = FakePluginLoader(
        {
            ws_plugin: _make_module("demo", config_received=config_received),
        }
    )

    ext_repo = StandaloneRepository(name="demo", path=ext_path)
    registry = PluginRegistry(fs, FakeConfigFileReader({}), loader).discover(workspace, standalone_repos=[ext_repo])

    # Workspace one loaded, extension one skipped (same name).
    assert loader.load_calls == [("demo", ws_plugin)]
    assert len(registry.plugins) == 1


def test_discover_skips_plugin_module_without_create_plugin(workspace: Workspace) -> None:
    """A module that doesn't export create_plugin() is silently skipped."""
    plugin_dir = WORKSPACE_ROOT / ".winter" / "plugins" / "broken"
    plugin_py = plugin_dir / "plugin.py"
    fs = FakeFilesystem(
        directories=[WORKSPACE_ROOT / ".winter" / "plugins", plugin_dir],
        files={plugin_py: ""},
    )
    loader = FakePluginLoader({plugin_py: ModuleType("broken")})  # no create_plugin

    registry = PluginRegistry(fs, FakeConfigFileReader({}), loader).discover(workspace, standalone_repos=[])
    assert registry.plugins == []
