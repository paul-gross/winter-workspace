from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import make_git_repo
from winter_cli.modules.workspace.internal.read_workspace_repository import (
    GREEK_LETTERS,
    ReadWorkspaceRepository,
    resolve_env_index,
)
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.models import ProjectRepository, Workspace


@pytest.fixture
def repo() -> ReadWorkspaceRepository:
    return ReadWorkspaceRepository(RepoErrorFactory())


def _project(name: str, workspace_root: Path) -> ProjectRepository:
    return ProjectRepository(
        name=name,
        main_path=workspace_root / "projects" / name,
        main_branch="main",
    )


def test_resolve_env_index_for_greek_letter_is_fixed() -> None:
    assert resolve_env_index("alpha") == 1
    assert resolve_env_index("beta") == 2
    assert resolve_env_index("omega") == len(GREEK_LETTERS)


def test_resolve_env_index_for_non_greek_is_deterministic() -> None:
    """Non-Greek names hash into the 26..281 bucket deterministically."""
    first = resolve_env_index("feature-x")
    second = resolve_env_index("feature-x")
    assert first == second
    assert 26 <= first < 26 + 256


def test_get_environments_discovers_greek_dirs_with_known_repos(tmp_path: Path, repo: ReadWorkspaceRepository) -> None:
    """Env discovery looks for Greek-letter dirs containing a known project repo subdir."""
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    (tmp_path / "alpha" / "demo").mkdir(parents=True)
    (tmp_path / "gamma" / "demo").mkdir(parents=True)
    # `delta` exists but doesn't contain the known repo — should be ignored.
    (tmp_path / "delta" / "other").mkdir(parents=True)

    envs = repo.get_environments(workspace, [_project("demo", tmp_path)])

    names = [e.name for e in envs]
    assert names == ["alpha", "gamma"]
    assert envs[0].index == 1
    assert envs[1].index == 3


def test_get_environment_status_reads_feature_branch_from_tracking(
    tmp_path: Path, repo: ReadWorkspaceRepository
) -> None:
    """Status reads `branch.<head>.{remote,merge}` from the first non-pinned worktree."""
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    env_dir = tmp_path / "alpha"
    env_dir.mkdir()
    worktree_path = env_dir / "demo"
    make_git_repo(worktree_path, initial_branch="alpha")

    # Wire tracking config that points at the canonical feature branch name.
    import git

    r = git.Repo(str(worktree_path))
    with r.config_writer(config_level="repository") as cw:
        cw.set_value('branch "alpha"', "remote", "origin")
        cw.set_value('branch "alpha"', "merge", "refs/heads/feature/widget")

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("demo", tmp_path)])

    assert status.feature_branch == "feature/widget"


def test_get_environment_status_returns_none_when_no_tracking(tmp_path: Path, repo: ReadWorkspaceRepository) -> None:
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    env_dir = tmp_path / "alpha"
    env_dir.mkdir()
    make_git_repo(env_dir / "demo", initial_branch="alpha")

    env = repo.get_environment(workspace, "alpha")
    status = repo.get_environment_status(env, [_project("demo", tmp_path)])

    assert status.feature_branch is None
