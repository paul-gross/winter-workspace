from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from winter_cli.config.internal import cwd_workspace_locator
from winter_cli.config.internal.cwd_workspace_locator import CwdWorkspaceLocator


def test_find_workspace_root_returns_directory_containing_winter_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace_root = tmp_path / "workspace"
    nested = workspace_root / "project" / "subdir"

    FakePath = MagicMock()
    FakePath.cwd.return_value = nested

    # Build a fake path hierarchy: nested -> project -> workspace_root (has .winter)
    fake_subdir = MagicMock()
    fake_subdir.__truediv__ = lambda self, name: MagicMock(is_dir=lambda: False)
    fake_subdir.parents = [
        MagicMock(__truediv__=lambda self, name: MagicMock(is_dir=lambda: False)),
        MagicMock(__truediv__=lambda self, name: MagicMock(is_dir=lambda: True)),
    ]
    FakePath.cwd.return_value = fake_subdir
    monkeypatch.setattr(cwd_workspace_locator, "Path", FakePath)

    # The locator should walk up until it finds .winter dir
    result = CwdWorkspaceLocator().find_workspace_root()

    assert result == fake_subdir.parents[1]


def test_find_workspace_root_raises_when_no_winter_dir_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePath = MagicMock()
    fake_cwd = MagicMock()
    fake_cwd.__truediv__ = lambda self, name: MagicMock(is_dir=lambda: False)
    # No parents find .winter
    fake_cwd.parents = [
        MagicMock(__truediv__=lambda self, name: MagicMock(is_dir=lambda: False)),
        MagicMock(__truediv__=lambda self, name: MagicMock(is_dir=lambda: False)),
    ]
    FakePath.cwd.return_value = fake_cwd
    monkeypatch.setattr(cwd_workspace_locator, "Path", FakePath)

    with pytest.raises(RuntimeError, match="Could not find workspace root"):
        CwdWorkspaceLocator().find_workspace_root()
