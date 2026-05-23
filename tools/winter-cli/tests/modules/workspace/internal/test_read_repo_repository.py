from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import git
import pytest

from winter_cli.modules.workspace.internal import read_repo_repository
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

_ROOT = Path("/fake/workspace")
_PROJECT_PATH = _ROOT / "projects" / "demo"
_EXT_PATH = _ROOT / "ext"
_ALPHA_PATH = _ROOT / "alpha"
_WT_PATH = _ALPHA_PATH / "demo"


def _fake_git_repo(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    git_mock = MagicMock()
    git_mock.GitCommandError = git.GitCommandError
    git_mock.InvalidGitRepositoryError = git.InvalidGitRepositoryError
    git_mock.NoSuchPathError = git.NoSuchPathError
    monkeypatch.setattr(read_repo_repository, "git", git_mock)
    return git_mock


@pytest.fixture
def repo() -> ReadRepoRepository:
    return ReadRepoRepository(RepoErrorFactory())


def _worktree(name: str = "demo", branch: str = "alpha") -> FeatureWorktree:
    workspace = Workspace(root_path=_ROOT, session_prefix="t", main_branch="main")
    env = FeatureEnvironment(workspace=workspace, name=branch, index=1, path=_ALPHA_PATH)
    project = ProjectRepository(name=name, main_path=_ALPHA_PATH / name, main_branch="main")
    return FeatureWorktree(workspace=workspace, environment=env, repository=project)


def test_get_project_status_reports_branch_and_clean_tree(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    project = ProjectRepository(name="demo", main_path=_PROJECT_PATH, main_branch="main")

    status = repo.get_project_status(project)

    assert status.name == "demo"
    assert status.branch == "main"
    assert status.dirty_files == []
    assert status.ahead == 0
    assert status.behind == 0


def test_get_project_status_lists_dirty_files(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    diff_item = MagicMock()
    diff_item.a_path = "README.md"
    r.index.diff.return_value = [diff_item]
    r.untracked_files = ["untracked.txt"]
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    project = ProjectRepository(name="demo", main_path=_PROJECT_PATH, main_branch="main")

    status = repo.get_project_status(project)

    assert "untracked.txt" in status.dirty_files
    assert "README.md" in status.dirty_files


def test_get_project_status_returns_empty_when_path_missing(repo: ReadRepoRepository) -> None:
    project = ProjectRepository(
        name="ghost",
        main_path=Path("/fake/does-not-exist/ghost"),
        main_branch="main",
    )
    status = repo.get_project_status(project)
    assert status.name == "ghost"
    assert status.branch is None
    assert status.dirty_files == []


def test_get_standalone_status_returns_empty_when_path_missing(repo: ReadRepoRepository) -> None:
    standalone = StandaloneRepository(name="ext", path=Path("/fake/does-not-exist/ext"))
    status = repo.get_standalone_status(standalone)
    assert status.name == "ext"
    assert status.branch is None


def test_get_standalone_status_reads_branch_and_commit(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    commit = MagicMock()
    commit.message = "init"
    r.head.commit = commit
    standalone = StandaloneRepository(name="ext", path=_EXT_PATH)

    status = repo.get_standalone_status(standalone)

    assert status.branch == "main"
    assert status.latest_commit == "init"


def test_get_worktree_status_delegates_to_repo_status(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    wt = _worktree()

    status = repo.get_worktree_status(wt)

    assert status.name == "demo"
    assert status.branch == "alpha"


def test_get_diff_for_uncommitted_returns_text_and_stats(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    r = git_mock.Repo.return_value
    diff_text = "diff --git a/demo/README.md b/demo/README.md\n--- a/demo/README.md\n+++ b/demo/README.md\n@@ -1 +1,2 @@\n+line\n"
    numstat_text = "1\t0\tREADME.md\n"
    r.git.diff.side_effect = [diff_text, numstat_text]
    wt = _worktree()

    result = repo.get_diff(wt, DiffMode.uncommitted)

    assert result.repo_name == "demo"
    assert result.diff_text == diff_text
    assert result.files_changed == 1


def test_get_workspace_constructs_domain_object(repo: ReadRepoRepository) -> None:
    workspace = repo.get_workspace(_ROOT, "test", "main")
    assert workspace.root_path == _ROOT
    assert workspace.session_prefix == "test"
    assert workspace.main_branch == "main"

