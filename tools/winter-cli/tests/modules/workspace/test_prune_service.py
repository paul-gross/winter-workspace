from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import make_git_repo
from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.modules.workspace.extensions import ExtensionService
from winter_cli.modules.workspace.prune_service import PruneOrphan, PruneService
from winter_cli.modules.workspace.repository_factory import RepositoryFactory


@pytest.fixture
def workspace_config(tmp_path: Path) -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=tmp_path,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
        project_repos=[
            ProjectRepositoryConfig(name="kept", url="git@example.com:org/kept.git"),
        ],
    )


@pytest.fixture
def service(workspace_config: WorkspaceConfig) -> PruneService:
    return PruneService(
        config=workspace_config,
        repo_factory=RepositoryFactory(workspace_config),
        extension_svc=ExtensionService(workspace_config),
    )


def test_find_orphans_returns_empty_when_projects_dir_missing(service: PruneService) -> None:
    assert service.find_orphans() == []


def test_find_orphans_flags_undeclared_clean_clone_as_safe(tmp_path: Path, service: PruneService) -> None:
    """An undeclared clone with a clean tree and no worktrees is safe to remove."""
    projects = tmp_path / "projects"
    projects.mkdir()
    orphan_path = projects / "ghost"
    make_git_repo(orphan_path, initial_branch="main")

    orphans = service.find_orphans()

    project_orphans = [o for o in orphans if o.kind == "project_clone"]
    assert len(project_orphans) == 1
    assert project_orphans[0].path == orphan_path
    assert project_orphans[0].safe_to_remove is True


def test_find_orphans_flags_dirty_clone_as_unsafe(tmp_path: Path, service: PruneService) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    orphan_path = projects / "dirty"
    make_git_repo(orphan_path, initial_branch="main")
    (orphan_path / "untracked.txt").write_text("hi\n")

    [orphan] = [o for o in service.find_orphans() if o.kind == "project_clone"]
    assert orphan.safe_to_remove is False
    assert "uncommitted or untracked" in orphan.notes


def test_remove_orphan_deletes_safe_clone(tmp_path: Path, service: PruneService) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    orphan_path = projects / "ghost"
    make_git_repo(orphan_path, initial_branch="main")

    [orphan] = service.find_orphans()
    service.remove_orphan(orphan)
    assert not orphan_path.exists()


def test_remove_orphan_refuses_unsafe(tmp_path: Path, service: PruneService) -> None:
    unsafe = PruneOrphan(kind="project_clone", path=tmp_path / "x", safe_to_remove=False, notes="dirty")
    with pytest.raises(RuntimeError, match="unsafe orphan"):
        service.remove_orphan(unsafe)
