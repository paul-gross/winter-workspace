from __future__ import annotations

from pathlib import Path

import pytest

from winter_cli.config.internal.write_winter_configuration_repository import (
    WriteWinterConfigurationRepository,
)
from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    StandaloneRepositoryConfig,
    WorkspaceConfig,
)


@pytest.fixture
def workspace_config(tmp_path: Path) -> WorkspaceConfig:
    (tmp_path / ".winter").mkdir()
    (tmp_path / ".winter" / "config.toml").write_text('main_branch = "main"\n')
    return WorkspaceConfig(
        workspace_root=tmp_path,
        session_prefix="test",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
    )


@pytest.fixture
def repo(workspace_config: WorkspaceConfig) -> WriteWinterConfigurationRepository:
    return WriteWinterConfigurationRepository(workspace_config)


def test_append_project_repository_adds_block(
    workspace_config: WorkspaceConfig, repo: WriteWinterConfigurationRepository
) -> None:
    repo.append_project_repository(
        ProjectRepositoryConfig(name="api", url="git@example.com:org/api.git", pinned=True),
    )
    content = (workspace_config.workspace_root / ".winter" / "config.toml").read_text()
    assert "[[project_repository]]" in content
    assert 'name = "api"' in content
    assert "pinned = true" in content


def test_append_standalone_repository_to_local_overlay(
    workspace_config: WorkspaceConfig, repo: WriteWinterConfigurationRepository
) -> None:
    """Local overlay file is auto-created on first write."""
    local_path = workspace_config.workspace_root / ".winter" / "config.local.toml"
    assert not local_path.exists()

    repo.append_standalone_repository(
        StandaloneRepositoryConfig(name="ext", url="git@example.com:org/ext.git"),
        local=True,
    )

    assert local_path.exists()
    content = local_path.read_text()
    assert "[[standalone_repository]]" in content
    assert 'name = "ext"' in content
    # Shared file untouched.
    assert "[[standalone_repository]]" not in (workspace_config.workspace_root / ".winter" / "config.toml").read_text()


def test_remove_project_repository_returns_true_when_found(
    workspace_config: WorkspaceConfig, repo: WriteWinterConfigurationRepository
) -> None:
    repo.append_project_repository(ProjectRepositoryConfig(name="api", url="git@example.com:org/api.git"))
    repo.append_project_repository(ProjectRepositoryConfig(name="web", url="git@example.com:org/web.git"))

    assert repo.remove_project_repository("api") is True
    content = (workspace_config.workspace_root / ".winter" / "config.toml").read_text()
    assert 'name = "api"' not in content
    assert 'name = "web"' in content


def test_remove_project_repository_returns_false_when_missing(repo: WriteWinterConfigurationRepository) -> None:
    assert repo.remove_project_repository("ghost") is False


def test_remove_matches_url_derived_name(
    workspace_config: WorkspaceConfig, repo: WriteWinterConfigurationRepository
) -> None:
    """When `name` is omitted on append, removal matches the URL-derived name."""
    repo.append_project_repository(ProjectRepositoryConfig(url="git@example.com:org/derived.git"))
    assert repo.remove_project_repository("derived") is True
