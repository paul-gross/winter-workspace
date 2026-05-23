from __future__ import annotations

from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from winter_cli.plugins.internal import importlib_plugin_loader
from winter_cli.plugins.internal.importlib_plugin_loader import ImportlibPluginLoader


def test_load_builds_spec_loads_module_and_registers_in_sys_modules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = tmp_path / "myplugin" / "__init__.py"

    fake_module = MagicMock(spec=ModuleType)
    fake_spec = MagicMock()
    fake_spec.name = "winter_plugin_myplugin"
    fake_spec.loader = MagicMock()

    fake_importlib = MagicMock()
    fake_importlib.util.spec_from_file_location.return_value = fake_spec
    fake_importlib.util.module_from_spec.return_value = fake_module

    fake_sys = MagicMock()
    fake_sys.modules = {}

    monkeypatch.setattr(importlib_plugin_loader, "importlib", fake_importlib)
    monkeypatch.setattr(importlib_plugin_loader, "sys", fake_sys)

    result = ImportlibPluginLoader.load("myplugin", entry)

    fake_importlib.util.spec_from_file_location.assert_called_once_with(
        "winter_plugin_myplugin",
        entry,
    )
    fake_importlib.util.module_from_spec.assert_called_once_with(fake_spec)
    assert fake_sys.modules["winter_plugin_myplugin"] is fake_module
    fake_spec.loader.exec_module.assert_called_once_with(fake_module)
    assert result is fake_module


def test_load_raises_import_error_when_spec_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = tmp_path / "bad_plugin" / "__init__.py"

    fake_importlib = MagicMock()
    fake_importlib.util.spec_from_file_location.return_value = None

    fake_sys = MagicMock()
    fake_sys.modules = {}

    monkeypatch.setattr(importlib_plugin_loader, "importlib", fake_importlib)
    monkeypatch.setattr(importlib_plugin_loader, "sys", fake_sys)

    with pytest.raises(ImportError, match="could not build module spec"):
        ImportlibPluginLoader.load("bad_plugin", entry)


def test_load_raises_import_error_when_loader_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = tmp_path / "no_loader" / "__init__.py"

    fake_spec = MagicMock()
    fake_spec.name = "winter_plugin_no_loader"
    fake_spec.loader = None

    fake_importlib = MagicMock()
    fake_importlib.util.spec_from_file_location.return_value = fake_spec

    fake_sys = MagicMock()
    fake_sys.modules = {}

    monkeypatch.setattr(importlib_plugin_loader, "importlib", fake_importlib)
    monkeypatch.setattr(importlib_plugin_loader, "sys", fake_sys)

    with pytest.raises(ImportError, match="could not build module spec"):
        ImportlibPluginLoader.load("no_loader", entry)
