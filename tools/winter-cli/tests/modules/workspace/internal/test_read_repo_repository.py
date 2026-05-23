from __future__ import annotations

from pathlib import Path

import git
import pytest

from tests.conftest import make_git_repo
from winter_cli.modules.workspace.internal.read_repo_repository import ReadRepoRepository
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.models import (
    DiffMode,
    FeatureEnvironment,
    FeatureWorktree,
    ProjectRepository,
    StandaloneRepository,
    Workspace,
)


@pytest.fixture
def repo() -> ReadRepoRepository:
    return ReadRepoRepository(RepoErrorFactory())


def _worktree(tmp_path: Path, name: str = "demo", branch: str = "alpha") -> FeatureWorktree:
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    env_dir = tmp_path / branch
    env_dir.mkdir(exist_ok=True)
    env = FeatureEnvironment(workspace=workspace, name=branch, index=1, path=env_dir)
    project = ProjectRepository(name=name, main_path=env_dir / name, main_branch="main")
    return FeatureWorktree(workspace=workspace, environment=env, repository=project)


def test_get_project_status_reports_branch_and_clean_tree(tmp_path: Path, repo: ReadRepoRepository) -> None:
    project_path = tmp_path / "projects" / "demo"
    project_path.parent.mkdir(parents=True)
    make_git_repo(project_path, initial_branch="main")
    project = ProjectRepository(name="demo", main_path=project_path, main_branch="main")

    status = repo.get_project_status(project)
    assert status.name == "demo"
    assert status.branch == "main"
    assert status.dirty_files == []
    # No `origin` configured, so ahead/behind probes fall through to 0.
    assert status.ahead == 0
    assert status.behind == 0


def test_get_project_status_lists_dirty_files(tmp_path: Path, repo: ReadRepoRepository) -> None:
    project_path = tmp_path / "projects" / "demo"
    project_path.parent.mkdir(parents=True)
    make_git_repo(project_path, initial_branch="main")
    (project_path / "untracked.txt").write_text("hi\n")
    (project_path / "README.md").write_text("changed\n")
    project = ProjectRepository(name="demo", main_path=project_path, main_branch="main")

    status = repo.get_project_status(project)
    assert "untracked.txt" in status.dirty_files
    assert "README.md" in status.dirty_files


def test_get_project_status_returns_empty_when_path_missing(tmp_path: Path, repo: ReadRepoRepository) -> None:
    """A missing source checkout is a legitimate 'not provisioned yet' state, not an error."""
    project = ProjectRepository(
        name="ghost",
        main_path=tmp_path / "projects" / "ghost",
        main_branch="main",
    )
    status = repo.get_project_status(project)
    assert status.name == "ghost"
    assert status.branch is None
    assert status.dirty_files == []


def test_get_standalone_status_returns_empty_when_path_missing(tmp_path: Path, repo: ReadRepoRepository) -> None:
    standalone = StandaloneRepository(name="ext", path=tmp_path / "ext")
    status = repo.get_standalone_status(standalone)
    assert status.name == "ext"
    assert status.branch is None


def test_get_standalone_status_reads_branch_and_commit(tmp_path: Path, repo: ReadRepoRepository) -> None:
    ext_path = tmp_path / "ext"
    make_git_repo(ext_path, initial_branch="main")
    standalone = StandaloneRepository(name="ext", path=ext_path)
    status = repo.get_standalone_status(standalone)
    assert status.branch == "main"
    assert status.latest_commit == "init"


def test_get_worktree_status_delegates_to_repo_status(tmp_path: Path, repo: ReadRepoRepository) -> None:
    wt = _worktree(tmp_path)
    make_git_repo(wt.path, initial_branch="alpha")
    status = repo.get_worktree_status(wt)
    assert status.name == "demo"
    assert status.branch == "alpha"


def test_get_diff_for_uncommitted_returns_text_and_stats(tmp_path: Path, repo: ReadRepoRepository) -> None:
    wt = _worktree(tmp_path)
    make_git_repo(wt.path, initial_branch="alpha")
    (wt.path / "README.md").write_text("modified content\nline two\n")

    result = repo.get_diff(wt, DiffMode.uncommitted)
    assert result.repo_name == "demo"
    assert result.diff_text  # non-empty
    assert result.files_changed == 1
    # The diff prefix carries the repo name.
    assert "a/demo/README.md" in result.diff_text


def test_get_workspace_constructs_domain_object(tmp_path: Path, repo: ReadRepoRepository) -> None:
    workspace = repo.get_workspace(tmp_path, "test", "main")
    assert workspace.root_path == tmp_path
    assert workspace.session_prefix == "test"
    assert workspace.main_branch == "main"


# Confirm GitPython itself doesn't lazy-import git in a way that would slow the
# test suite; if it ever changes the symbol surface, surface that here.
def test_git_module_is_importable() -> None:
    assert hasattr(git, "Repo")
