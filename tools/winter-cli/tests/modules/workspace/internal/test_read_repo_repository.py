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
    RepoError,
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
    # The implementation uses `with git.Repo(...) as r:`, so __enter__ must return
    # the same mock that tests assert against.
    git_mock.Repo.return_value.__enter__.return_value = git_mock.Repo.return_value
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


def test_get_project_status_lists_dirty_files(monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    diff_item = MagicMock()
    diff_item.a_path = "README.md"
    # "HEAD" → staged diff; None → unstaged diff. README.md is unstaged only here.
    r.index.diff.side_effect = lambda arg: [] if arg == "HEAD" else [diff_item]
    r.untracked_files = ["untracked.txt"]
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    project = ProjectRepository(name="demo", main_path=_PROJECT_PATH, main_branch="main")

    status = repo.get_project_status(project)

    assert "untracked.txt" in status.dirty_files
    assert "README.md" in status.dirty_files


def test_get_project_status_counts_staged_files_as_dirty(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    staged_item = MagicMock()
    staged_item.a_path = "staged.py"
    # "HEAD" → staged diff only; None → no unstaged changes.
    r.index.diff.side_effect = lambda arg: [staged_item] if arg == "HEAD" else []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    project = ProjectRepository(name="demo", main_path=_PROJECT_PATH, main_branch="main")

    status = repo.get_project_status(project)

    assert "staged.py" in status.dirty_files
    assert len(status.dirty_files) == 1


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


def test_get_standalone_status_counts_staged_files_as_dirty(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    staged_item = MagicMock()
    staged_item.a_path = "staged.py"
    # "HEAD" → staged diff only; None → no unstaged changes.
    r.index.diff.side_effect = lambda arg: [staged_item] if arg == "HEAD" else []
    r.untracked_files = []
    commit = MagicMock()
    commit.message = "init"
    r.head.commit = commit
    standalone = StandaloneRepository(name="ext", path=_EXT_PATH)

    status = repo.get_standalone_status(standalone)

    assert status.dirty_count == 1


def test_get_standalone_detail_lists_head_commits(monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository) -> None:
    # A standalone has no feature branch ahead of main, so the detail view lists
    # the tip commits on HEAD itself — and must do so even with no main_branch.
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "main"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    commit = MagicMock()
    commit.hexsha = "abcdef1234567"
    commit.message = "recent work\n\nbody"
    r.iter_commits.return_value = [commit]
    standalone = StandaloneRepository(name="ext", path=_EXT_PATH)  # main_branch=None

    status = repo.get_standalone_detail(standalone)

    assert status.name == "ext"
    assert status.branch == "main"
    assert len(status.recent_commits) == 1
    assert status.recent_commits[0].short_hash == "abcdef1"
    assert status.recent_commits[0].message == "recent work"
    r.iter_commits.assert_called_once_with("HEAD", max_count=10)


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


def test_get_worktree_status_builds_commit_graph(monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository) -> None:
    # A feature worktree graphs the divergence from origin/<main> with --boundary
    # so the merge-base commit anchors the history.
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    r.git.log.return_value = "* abc1234 feature work\no def5678 base"
    wt = _worktree()

    status = repo.get_worktree_status(wt)

    assert status.commit_graph == ["* abc1234 feature work", "o def5678 base"]
    r.git.log.assert_called_once_with("--graph", "--oneline", "--decorate", "--boundary", "origin/main..HEAD")


def test_commit_graph_falls_back_to_head_when_main_ref_missing(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    # Fresh clone with no origin/main yet: the boundary range raises, the ref
    # verify confirms it's genuinely missing, and the HEAD graph is used instead.
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []

    def _log(*args: str) -> str:
        if "origin/main..HEAD" in args:
            raise git.GitCommandError("log", 128)
        return "* abc1234 only commit"

    r.git.log.side_effect = _log
    r.git.rev_parse.side_effect = git.GitCommandError("rev-parse", 1)
    wt = _worktree()

    status = repo.get_worktree_status(wt)

    assert status.commit_graph == ["* abc1234 only commit"]
    r.git.log.assert_any_call("--graph", "--oneline", "--decorate", "--max-count=30", "HEAD")


def test_commit_graph_raises_when_present_main_ref_fails(
    monkeypatch: pytest.MonkeyPatch, repo: ReadRepoRepository
) -> None:
    # The main ref resolves but `git log` still fails — a real error, not the
    # tolerated missing-ref case, so it propagates as a RepoError.
    git_mock = _fake_git_repo(monkeypatch)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    r.active_branch.tracking_branch.return_value = None
    r.index.diff.return_value = []
    r.untracked_files = []
    r.git.rev_list.return_value = "0"
    r.iter_commits.return_value = []
    r.git.log.side_effect = git.GitCommandError("log", 128)
    r.git.rev_parse.return_value = "deadbeef"  # ref present
    wt = _worktree()

    with pytest.raises(RepoError):
        repo.get_worktree_status(wt)


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
