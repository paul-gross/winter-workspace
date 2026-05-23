from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeFilesystem
from winter_cli.config.internal.write_winter_configuration_repository import (
    WriteWinterConfigurationRepository,
)
from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    StandaloneRepositoryConfig,
    WorkspaceConfig,
)

WORKSPACE_ROOT = Path("/ws")
SHARED_CONFIG = WORKSPACE_ROOT / ".winter" / "config.toml"
LOCAL_CONFIG = WORKSPACE_ROOT / ".winter" / "config.local.toml"


@pytest.fixture
def workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=WORKSPACE_ROOT,
        session_prefix="test",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
    )


@pytest.fixture
def fs() -> FakeFilesystem:
    return FakeFilesystem(files={SHARED_CONFIG: 'main_branch = "main"\n'})


@pytest.fixture
def repo(workspace_config: WorkspaceConfig, fs: FakeFilesystem) -> WriteWinterConfigurationRepository:
    return WriteWinterConfigurationRepository(workspace_config, fs=fs)


def test_append_project_repository_adds_block(fs: FakeFilesystem, repo: WriteWinterConfigurationRepository) -> None:
    repo.append_project_repository(
        ProjectRepositoryConfig(name="api", url="git@example.com:org/api.git", pinned=True),
    )
    content = fs.files[SHARED_CONFIG]
    assert "[[project_repository]]" in content
    assert 'name = "api"' in content
    assert "pinned = true" in content


def test_append_standalone_repository_to_local_overlay(
    fs: FakeFilesystem, repo: WriteWinterConfigurationRepository
) -> None:
    """Local overlay file is auto-created on first write."""
    assert LOCAL_CONFIG not in fs.files

    repo.append_standalone_repository(
        StandaloneRepositoryConfig(name="ext", url="git@example.com:org/ext.git"),
        local=True,
    )

    assert LOCAL_CONFIG in fs.files
    content = fs.files[LOCAL_CONFIG]
    assert "[[standalone_repository]]" in content
    assert 'name = "ext"' in content
    # Shared file untouched.
    assert "[[standalone_repository]]" not in fs.files[SHARED_CONFIG]


def test_remove_project_repository_returns_true_when_found(
    fs: FakeFilesystem, repo: WriteWinterConfigurationRepository
) -> None:
    repo.append_project_repository(ProjectRepositoryConfig(name="api", url="git@example.com:org/api.git"))
    repo.append_project_repository(ProjectRepositoryConfig(name="web", url="git@example.com:org/web.git"))

    assert repo.remove_project_repository("api") is True
    content = fs.files[SHARED_CONFIG]
    assert 'name = "api"' not in content
    assert 'name = "web"' in content


def test_remove_project_repository_returns_false_when_missing(repo: WriteWinterConfigurationRepository) -> None:
    assert repo.remove_project_repository("ghost") is False


def test_remove_matches_url_derived_name(fs: FakeFilesystem, repo: WriteWinterConfigurationRepository) -> None:
    """When `name` is omitted on append, removal matches the URL-derived name."""
    repo.append_project_repository(ProjectRepositoryConfig(url="git@example.com:org/derived.git"))
    assert repo.remove_project_repository("derived") is True
