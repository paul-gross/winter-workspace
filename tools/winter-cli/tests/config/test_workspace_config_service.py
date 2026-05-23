from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from winter_cli.config.models import AdoptExtensions, SingletonType
from winter_cli.config.workspace import WorkspaceConfigService


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A bare workspace with a single project repo declared in `.winter/config.toml`."""
    (tmp_path / ".winter").mkdir()
    (tmp_path / ".winter" / "config.toml").write_text(
        dedent(
            """
            main_branch = "trunk"
            session_prefix = "ws"
            git_excludes = ["/.idea/"]

            [git.user]
            name = "Test User"
            email = "test@example.com"

            [[project_repository]]
            name = "frontend"
            url = "git@example.com:org/frontend.git"
            pinned = true

            [[standalone_repository]]
            name = "ext-one"
            url = "git@example.com:org/ext-one.git"
            """
        ).strip()
        + "\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_load_reads_shared_config(workspace_dir: Path) -> None:
    config = WorkspaceConfigService().load()

    assert config.workspace_root == workspace_dir
    assert config.session_prefix == "ws"
    assert config.main_branch == "trunk"
    assert config.git_excludes == ["/.idea/"]
    assert config.git_identity is not None
    assert config.git_identity.name == "Test User"
    assert config.git_identity.email == "test@example.com"
    assert config.adopt_extensions == AdoptExtensions.winter

    # Workspace singleton is always materialized from the workspace dir name.
    assert any(r.type == SingletonType.workspace for r in config.singleton_repos)

    assert len(config.project_repos) == 1
    assert config.project_repos[0].name == "frontend"
    assert config.project_repos[0].pinned is True

    assert len(config.standalone_repos) == 1
    assert config.standalone_repos[0].name == "ext-one"


def test_load_merges_local_overlay(workspace_dir: Path) -> None:
    (workspace_dir / ".winter" / "config.local.toml").write_text(
        dedent(
            """
            main_branch = "develop"

            [[project_repository]]
            name = "backend"
            url = "git@example.com:org/backend.git"
            """
        ).strip()
        + "\n"
    )

    config = WorkspaceConfigService().load()

    # Scalars in the overlay win.
    assert config.main_branch == "develop"
    # Arrays of tables concatenate (deep_merge behavior).
    names = sorted(r.name for r in config.project_repos if r.name)
    assert names == ["backend", "frontend"]


def test_load_rejects_invalid_adopt_extensions(workspace_dir: Path) -> None:
    (workspace_dir / ".winter" / "config.toml").write_text('adopt_extensions = "bogus"\n')
    with pytest.raises(RuntimeError, match="adopt_extensions"):
        WorkspaceConfigService().load()
