from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import git
import pytest

from winter_cli.modules.workspace.env_index import GREEK_LETTERS, resolve_env_index
from winter_cli.modules.workspace.internal import read_workspace_repository
from winter_cli.modules.workspace.internal.branch_tracking import feature_branch_from_upstream
from winter_cli.modules.workspace.internal.read_repo_repository import _parse_status_porcelain_v2
from winter_cli.modules.workspace.internal.read_workspace_repository import (
    ReadWorkspaceRepository,
)
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.models import FeatureEnvironment, ProjectRepository, Workspace

_ROOT = Path("/fake/workspace")


def _fake_git_repo(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    git_mock = MagicMock()
    git_mock.GitCommandError = git.GitCommandError
    git_mock.InvalidGitRepositoryError = git.InvalidGitRepositoryError
    git_mock.NoSuchPathError = git.NoSuchPathError
    # The implementation uses `with git.Repo(...) as r:`, so __enter__ must return
    # the same mock that tests assert against.
    git_mock.Repo.return_value.__enter__.return_value = git_mock.Repo.return_value
    monkeypatch.setattr(read_workspace_repository, "git", git_mock)
    return git_mock


@pytest.fixture
def repo() -> ReadWorkspaceRepository:
    return ReadWorkspaceRepository(RepoErrorFactory())


def _project(name: str) -> ProjectRepository:
    return ProjectRepository(
        name=name,
        main_path=_ROOT / "projects" / name,
        main_branch="main",
    )


def test_resolve_env_index_for_greek_letter_is_fixed() -> None:
    # With the full GREEK_LETTERS list as aliases, alpha→1 and omega→24.
    assert resolve_env_index("alpha", GREEK_LETTERS, 48) == 1
    assert resolve_env_index("beta", GREEK_LETTERS, 48) == 2
    assert resolve_env_index("omega", GREEK_LETTERS, 48) == len(GREEK_LETTERS)


def test_resolve_env_index_for_non_greek_is_deterministic() -> None:
    # With the full 24-letter list as aliases and 48 envs, the hash band is
    # 26..48 (N=24, buffer=25, band=26..48).  Non-alias names hash
    # deterministically into that range.
    first = resolve_env_index("feature-x", GREEK_LETTERS, 48)
    second = resolve_env_index("feature-x", GREEK_LETTERS, 48)
    assert first == second
    assert 26 <= first <= 48


def test_get_environments_discovers_greek_dirs_with_known_repos(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")

    # alpha/ and gamma/ contain "demo"; delta/ contains only "other".
    def _is_dir(self: Path) -> bool:
        existing = {
            _ROOT / "alpha",
            _ROOT / "alpha" / "demo",
            _ROOT / "gamma",
            _ROOT / "gamma" / "demo",
            _ROOT / "delta",
            _ROOT / "delta" / "other",
        }
        return self in existing

    def _iterdir(self: Path) -> list[Path]:
        contents: dict[Path, list[Path]] = {
            _ROOT / "alpha": [_ROOT / "alpha" / "demo"],
            _ROOT / "gamma": [_ROOT / "gamma" / "demo"],
            _ROOT / "delta": [_ROOT / "delta" / "other"],
        }
        return contents.get(self, [])

    monkeypatch.setattr(Path, "is_dir", _is_dir)
    monkeypatch.setattr(Path, "iterdir", _iterdir)

    envs = repo.get_environments(workspace, [_project("demo")])

    names = [e.name for e in envs]
    assert names == ["alpha", "gamma"]
    assert envs[0].index == 1
    assert envs[1].index == 3


def test_get_environments_discovers_non_greek_env_from_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hyphenated env (e.g. `feature-xyz`) recorded in the registry is discovered."""
    registry = MagicMock()
    registry.all_assignments.return_value = {"alpha": 1, "feature-xyz": 30}
    registry.get_index.side_effect = lambda name: {"alpha": 1, "feature-xyz": 30}.get(name)
    repo = ReadWorkspaceRepository(RepoErrorFactory(), registry=registry)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")

    def _is_dir(self: Path) -> bool:
        existing = {
            _ROOT / "alpha",
            _ROOT / "alpha" / "demo",
            _ROOT / "feature-xyz",
            _ROOT / "feature-xyz" / "demo",
        }
        return self in existing

    def _iterdir(self: Path) -> list[Path]:
        contents: dict[Path, list[Path]] = {
            _ROOT / "alpha": [_ROOT / "alpha" / "demo"],
            _ROOT / "feature-xyz": [_ROOT / "feature-xyz" / "demo"],
        }
        return contents.get(self, [])

    monkeypatch.setattr(Path, "is_dir", _is_dir)
    monkeypatch.setattr(Path, "iterdir", _iterdir)

    envs = repo.get_environments(workspace, [_project("demo")])

    # Ordered by index: alpha (1) then feature-xyz (30).
    assert [e.name for e in envs] == ["alpha", "feature-xyz"]
    assert [e.index for e in envs] == [1, 30]


def test_get_environment_status_reads_feature_branch_from_tracking(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")
    worktree_path = _ROOT / "alpha" / "demo"

    # The adapter checks (worktree_path / ".git").exists()
    monkeypatch.setattr(Path, "exists", lambda self: self == worktree_path / ".git")

    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    r.git.config.side_effect = ["origin", "refs/heads/feature/widget"]

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("demo")])

    assert status.feature_branch == "feature/widget"


def test_get_environment_status_returns_none_when_no_tracking(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")
    worktree_path = _ROOT / "alpha" / "demo"

    monkeypatch.setattr(Path, "exists", lambda self: self == worktree_path / ".git")

    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    config_not_found = git.GitCommandError(("git", "config", "--get"), 1, stderr=b"")
    config_not_found.status = 1
    r.git.config.side_effect = config_not_found

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("demo")])

    assert status.feature_branch is None
    assert status.distinct_remote_count == 0


def test_get_environment_status_counts_distinct_remotes_across_worktrees(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    """Two non-pinned worktrees on different branches → primary is the first, distinct count is 2."""
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")

    monkeypatch.setattr(Path, "exists", lambda self: self.name == ".git")

    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    # Two config reads (remote, merge) per worktree, in repo order: api, web.
    r.git.config.side_effect = [
        "origin",
        "refs/heads/feature/auth",
        "origin",
        "refs/heads/feature/billing",
    ]

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("api"), _project("web")])

    assert status.feature_branch == "feature/auth"
    assert status.distinct_remote_count == 2


def test_get_environment_status_shared_branch_counts_one_distinct_remote(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    """Two non-pinned worktrees on the *same* branch → a single distinct remote (no `+N`)."""
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")

    monkeypatch.setattr(Path, "exists", lambda self: self.name == ".git")

    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    r.git.config.side_effect = [
        "origin",
        "refs/heads/feature/widget",
        "origin",
        "refs/heads/feature/widget",
    ]

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("api"), _project("web")])

    assert status.feature_branch == "feature/widget"
    assert status.distinct_remote_count == 1


def test_get_environment_status_primary_is_first_connected_repo(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    """When the leading non-pinned repo is disconnected, the primary is the next connected one."""
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")

    monkeypatch.setattr(Path, "exists", lambda self: self.name == ".git")

    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    # First repo (api) has no upstream config (exit 1); second repo (web) tracks a branch.
    config_not_found = git.GitCommandError(("git", "config", "--get"), 1, stderr=b"")
    config_not_found.status = 1
    r.git.config.side_effect = [
        config_not_found,  # api: branch.alpha.remote not set
        "origin",  # web: remote
        "refs/heads/feature/web",  # web: merge
    ]

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("api"), _project("web")])

    assert status.feature_branch == "feature/web"
    assert status.distinct_remote_count == 1


def test_get_environment_status_excludes_pinned_from_distinct_count(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    """A pinned repo tracks main and is never read — it doesn't inflate the distinct count."""
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")

    monkeypatch.setattr(Path, "exists", lambda self: self.name == ".git")

    r = git_mock.Repo.return_value
    r.active_branch.name = "alpha"
    # Only the single non-pinned repo is read (two config calls).
    r.git.config.side_effect = ["origin", "refs/heads/feature/auth"]

    pinned = ProjectRepository(name="pinned", main_path=_ROOT / "projects" / "pinned", main_branch="main", pinned=True)

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("api"), pinned])

    assert status.feature_branch == "feature/auth"
    assert status.distinct_remote_count == 1


# --------------------------------------------------------------------------- #
# get_environment_status with worktree_tracking — porcelain-derived branch,
# no git.Repo open at all (the duplicate-open elimination this issue targets).
# --------------------------------------------------------------------------- #


def test_get_environment_status_with_worktree_tracking_opens_no_repo(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")
    env = repo.get_environment(workspace, "alpha")

    status = repo.get_environment_status(
        env,
        [_project("api"), _project("web")],
        worktree_tracking={"api": "origin/feature/auth", "web": "origin/feature/auth"},
    )

    assert status.feature_branch == "feature/auth"
    assert status.distinct_remote_count == 1
    git_mock.Repo.assert_not_called()


def test_get_environment_status_with_worktree_tracking_excludes_other_remotes(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")
    env = repo.get_environment(workspace, "alpha")

    status = repo.get_environment_status(
        env,
        [_project("api")],
        worktree_tracking={"api": "upstream/feature/auth"},
    )

    assert status.feature_branch is None
    assert status.distinct_remote_count == 0


def test_get_environment_status_with_worktree_tracking_excludes_pinned(
    monkeypatch: pytest.MonkeyPatch, repo: ReadWorkspaceRepository
) -> None:
    _fake_git_repo(monkeypatch)
    workspace = Workspace(root_path=_ROOT, service_prefix="t", main_branch="main")
    env = repo.get_environment(workspace, "alpha")
    pinned = ProjectRepository(name="pinned", main_path=_ROOT / "projects" / "pinned", main_branch="main", pinned=True)

    status = repo.get_environment_status(
        env,
        [_project("api"), pinned],
        # No entry for "pinned" — a pinned repo is never consulted, so a missing
        # dict entry can't accidentally surface as its feature branch.
        worktree_tracking={"api": "origin/feature/auth"},
    )

    assert status.feature_branch == "feature/auth"
    assert status.distinct_remote_count == 1


# --------------------------------------------------------------------------- #
# feature_branch_from_upstream — pure porcelain-value transform
# --------------------------------------------------------------------------- #


class TestFeatureBranchFromUpstream:
    def test_none_is_disconnected(self) -> None:
        assert feature_branch_from_upstream(None) is None

    def test_origin_remote_returns_bare_branch(self) -> None:
        assert feature_branch_from_upstream("origin/feature/widget") == "feature/widget"

    def test_non_origin_remote_returns_none(self) -> None:
        assert feature_branch_from_upstream("upstream/feature/widget") is None

    def test_value_with_no_slash_returns_none(self) -> None:
        assert feature_branch_from_upstream("origin") is None


# --------------------------------------------------------------------------- #
# End-to-end against real git repos: the porcelain-derived feature branch
# (get_environment_status with worktree_tracking, fed by _parse_status_porcelain_v2)
# matches the old direct-config read (get_environment_status with no
# worktree_tracking) for every state — connected, other-remote, disconnected,
# detached, and unborn HEAD.
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_repo(path: Path, branch: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", branch)
    _git(path, "config", "user.email", "t@t.com")
    _git(path, "config", "user.name", "tester")
    # `branch.upstream` is only printed by porcelain-v2 once the `origin` remote
    # itself is known to git — matching every real worktree in this codebase,
    # which is always an `origin` clone.
    _git(path, "remote", "add", "origin", "https://example.invalid/repo.git")


def _commit(path: Path, filename: str, content: str, message: str) -> None:
    (path / filename).write_text(content)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", message)


def _real_status_and_tracking_branch(repo_path: Path) -> str | None:
    """The status piece's porcelain `tracking_branch` — what a caller would
    already have gathered elsewhere in the same refresh."""
    out = _git(
        repo_path,
        "status",
        "--porcelain=v2",
        "--branch",
        "--untracked-files=all",
        "-z",
    )
    return _parse_status_porcelain_v2(out).tracking_branch


def _compare_old_and_new(repo_path: Path, repo_name: str) -> None:
    """Old direct-config read vs. new porcelain-derived read must agree."""
    workspace = Workspace(root_path=repo_path.parent, service_prefix="t", main_branch="main")
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=repo_path.parent)
    project = ProjectRepository(name=repo_name, main_path=repo_path, main_branch="main")
    real_repo = ReadWorkspaceRepository(RepoErrorFactory())

    old_status = real_repo.get_environment_status(env, [project])

    tracking = {repo_name: _real_status_and_tracking_branch(repo_path)}
    new_status = real_repo.get_environment_status(env, [project], worktree_tracking=tracking)

    assert new_status.feature_branch == old_status.feature_branch


def test_real_connected_origin_unfetched_matches_old_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "demo"
    _init_repo(repo_path, "feature-x")
    _git(repo_path, "config", "branch.feature-x.remote", "origin")
    _git(repo_path, "config", "branch.feature-x.merge", "refs/heads/feature/x")

    _compare_old_and_new(repo_path, "demo")


def test_real_connected_origin_fetched_matches_old_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "demo"
    _init_repo(repo_path, "feature-x")
    _commit(repo_path, "f.txt", "1\n", "init")
    _git(repo_path, "config", "branch.feature-x.remote", "origin")
    _git(repo_path, "config", "branch.feature-x.merge", "refs/heads/feature/x")
    _git(repo_path, "update-ref", "refs/remotes/origin/feature/x", "HEAD")

    _compare_old_and_new(repo_path, "demo")


def test_real_other_remote_matches_old_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "demo"
    _init_repo(repo_path, "feature-z")
    _git(repo_path, "remote", "add", "upstream", "https://example.invalid/upstream.git")
    _git(repo_path, "config", "branch.feature-z.remote", "upstream")
    _git(repo_path, "config", "branch.feature-z.merge", "refs/heads/feature/z")

    _compare_old_and_new(repo_path, "demo")


def test_real_disconnected_matches_old_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "demo"
    _init_repo(repo_path, "feature-none")
    _commit(repo_path, "f.txt", "1\n", "init")

    _compare_old_and_new(repo_path, "demo")


def test_real_detached_head_matches_old_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "demo"
    _init_repo(repo_path, "feature-d")
    _commit(repo_path, "f.txt", "1\n", "init")
    _git(repo_path, "checkout", "-q", "--detach")

    _compare_old_and_new(repo_path, "demo")


def test_real_unborn_head_with_upstream_matches_old_path(tmp_path: Path) -> None:
    repo_path = tmp_path / "demo"
    _init_repo(repo_path, "feature-u")
    _git(repo_path, "config", "branch.feature-u.remote", "origin")
    _git(repo_path, "config", "branch.feature-u.merge", "refs/heads/feature/u")

    _compare_old_and_new(repo_path, "demo")
