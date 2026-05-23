from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from winter_cli.modules.workspace.env_status_service import EnvStatusService
from winter_cli.modules.workspace.models import (
    FeatureEnvironment,
    FeatureEnvironmentStatus,
    FeatureWorktree,
    ProjectRepository,
    Workspace,
)

WORKSPACE_ROOT = Path("/ws")


@pytest.fixture
def workspace() -> Workspace:
    return Workspace(root_path=WORKSPACE_ROOT, session_prefix="t", main_branch="main")


class FakeReadWorkspaceRepository:
    """Stub for the `IReadWorkspaceRepository` Protocol — returns canned status."""

    def __init__(self, feature_branch: str | None = None) -> None:
        self._feature_branch = feature_branch

    def get_environments(
        self, workspace: Workspace, project_repos: list[ProjectRepository]
    ) -> list[FeatureEnvironment]:
        return []

    def get_environment(self, workspace: Workspace, name: str) -> FeatureEnvironment:
        return FeatureEnvironment(workspace=workspace, name=name, index=1, path=workspace.root_path / name)

    def get_environment_status(
        self, env: FeatureEnvironment, project_repos: list[ProjectRepository]
    ) -> FeatureEnvironmentStatus:
        return FeatureEnvironmentStatus(environment=env, feature_branch=self._feature_branch)


class FakeWriteRepoRepository:
    """Stub for the `IWriteRepoRepository` Protocol — raises on any unexpected call."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"FakeWriteRepoRepository.{name} called unexpectedly")


def _service(feature_branch: str | None = None) -> EnvStatusService:
    return EnvStatusService(
        worktree_repo=FakeReadWorkspaceRepository(feature_branch=feature_branch),  # type: ignore[arg-type]
        repo_repo=FakeWriteRepoRepository(),  # type: ignore[arg-type]
    )


def test_get_feature_environment_worktrees_builds_one_per_repo(workspace: Workspace) -> None:
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=workspace.root_path / "alpha")
    repos = [
        ProjectRepository(name="r1", main_path=workspace.root_path / "projects" / "r1", main_branch="main"),
        ProjectRepository(name="r2", main_path=workspace.root_path / "projects" / "r2", main_branch="main"),
    ]

    env_wts = _service().get_feature_environment_worktrees(env, repos)

    assert env_wts.environment is env
    assert [wt.repository.name for wt in env_wts.worktrees] == ["r1", "r2"]
    assert env_wts.worktrees[0].path == workspace.root_path / "alpha" / "r1"


def test_get_feature_worktree_pairs_env_and_repo(workspace: Workspace) -> None:
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=workspace.root_path / "alpha")
    repo = ProjectRepository(name="demo", main_path=workspace.root_path / "projects" / "demo", main_branch="main")
    wt = _service().get_feature_worktree(env, repo)
    assert isinstance(wt, FeatureWorktree)
    assert wt.repository.name == "demo"
    assert wt.environment.name == "alpha"


def test_get_environment_status_delegates_to_worktree_repo(workspace: Workspace) -> None:
    """The service returns the status verbatim when no env decorators are supplied."""
    svc = _service(feature_branch="feature/x")
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=workspace.root_path / "alpha")

    status = svc.get_environment_status(env, project_repos=[])
    assert status.feature_branch == "feature/x"
