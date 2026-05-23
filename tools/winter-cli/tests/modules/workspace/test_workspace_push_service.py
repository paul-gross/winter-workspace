from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.modules.workspace.env_status_service import EnvStatusService
from winter_cli.modules.workspace.models import (
    FeatureEnvironment,
    FeatureEnvironmentStatus,
    ProjectRepository,
    RepoScope,
    Workspace,
)
from winter_cli.modules.workspace.repository_factory import RepositoryFactory
from winter_cli.modules.workspace.workspace_push_service import WorkspacePushService

WORKSPACE_ROOT = Path("/ws")


@pytest.fixture
def workspace() -> Workspace:
    return Workspace(root_path=WORKSPACE_ROOT, session_prefix="t", main_branch="main")


@pytest.fixture
def workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=WORKSPACE_ROOT,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
        project_repos=[
            ProjectRepositoryConfig(name="demo", url="git@example.com:org/demo.git"),
        ],
    )


class FakeReadWorkspaceRepository:
    def get_environments(
        self, workspace: Workspace, project_repos: list[ProjectRepository]
    ) -> list[FeatureEnvironment]:
        return []

    def get_environment_status(
        self, env: FeatureEnvironment, project_repos: list[ProjectRepository]
    ) -> FeatureEnvironmentStatus:
        return FeatureEnvironmentStatus(environment=env, feature_branch=None)


class FakeWriteRepoRepository:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"FakeWriteRepoRepository.{name} called unexpectedly")


def test_push_all_with_no_envs_returns_empty_report(workspace: Workspace, workspace_config: WorkspaceConfig) -> None:
    """Smoke: push_all returns an empty report when the workspace has no envs or standalones."""
    fake_worktree_repo = FakeReadWorkspaceRepository()
    fake_repo_repo = FakeWriteRepoRepository()
    env_status_svc = EnvStatusService(
        worktree_repo=fake_worktree_repo,  # type: ignore[arg-type]
        repo_repo=fake_repo_repo,  # type: ignore[arg-type]
    )
    svc = WorkspacePushService(
        env_status_svc=env_status_svc,
        worktree_repo=fake_worktree_repo,  # type: ignore[arg-type]
        repo_repo=fake_repo_repo,  # type: ignore[arg-type]
        repo_factory=RepositoryFactory(workspace_config),
        workspace=workspace,
    )

    report = svc.push_all(scope=RepoScope.project, patterns=None)
    assert report.envs == []
    assert report.standalone == []
    assert report.skipped == []
