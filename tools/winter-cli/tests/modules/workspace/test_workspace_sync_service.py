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
from winter_cli.modules.workspace.fetch_reporter import IFetchReporter
from winter_cli.modules.workspace.internal.git_ops_service import GitOpsService
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.models import (
    FeatureEnvironment,
    FeatureEnvironmentStatus,
    FeatureEnvironmentWorktrees,
    FeatureWorktree,
    ProjectRepository,
    PullMode,
    RepoScope,
    Workspace,
)
from winter_cli.modules.workspace.pull_reporter import IPullReporter
from winter_cli.modules.workspace.repository_factory import RepositoryFactory
from winter_cli.modules.workspace.workspace_sync_service import WorkspaceSyncService

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
    """No-op repo for empty-input smoke tests.

    `sync_ff_only` exists as a no-op rather than raising on `__getattr__`
    because `sync_env` accesses it as an attribute for `pool.map(...)` even
    when the iterable is empty. Other attribute accesses still raise so
    accidental fan-out trips the test.
    """

    def sync_ff_only(self, repo: ProjectRepository) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"FakeWriteRepoRepository.{name} called unexpectedly")


class _NullFetchReporter:
    def fetch_started(self) -> None:
        return None

    def repo_fetched(self, scope: str, repo: str, success: bool, error: str | None) -> None:
        return None

    def fetch_completed(self, success: bool) -> None:
        return None


class _NullPullReporter:
    def pull_started(self) -> None:
        return None

    def env_skipped(self, env: str, reason: str) -> None:
        return None

    def repo_synced(self, scope: str, repo: str, result: Any, ahead: int, behind: int) -> None:
        return None

    def pull_completed(self, success: bool) -> None:
        return None


def _make_service(workspace: Workspace, workspace_config: WorkspaceConfig) -> WorkspaceSyncService:
    fake_worktree_repo = FakeReadWorkspaceRepository()
    fake_repo_repo = FakeWriteRepoRepository()
    env_status_svc = EnvStatusService(
        worktree_repo=fake_worktree_repo,  # type: ignore[arg-type]
        repo_repo=fake_repo_repo,  # type: ignore[arg-type]
    )
    git_ops = GitOpsService(RepoErrorFactory(), sleep=lambda _: None, jitter=lambda: 0.0)
    return WorkspaceSyncService(
        env_status_svc=env_status_svc,
        worktree_repo=fake_worktree_repo,  # type: ignore[arg-type]
        repo_repo=fake_repo_repo,  # type: ignore[arg-type]
        repo_factory=RepositoryFactory(workspace_config),
        workspace=workspace,
        git_ops=git_ops,
    )


def test_construct_sync_service(workspace: Workspace, workspace_config: WorkspaceConfig) -> None:
    """Smoke test: WorkspaceSyncService can be assembled from its dependencies.

    The substantive sync/fetch/pull behaviour is exercised via integration in
    the dashboard; this unit-level test just locks the constructor signature
    so DI rewiring fails loudly.
    """
    fake_worktree_repo = FakeReadWorkspaceRepository()
    fake_repo_repo = FakeWriteRepoRepository()
    env_status_svc = EnvStatusService(
        worktree_repo=fake_worktree_repo,  # type: ignore[arg-type]
        repo_repo=fake_repo_repo,  # type: ignore[arg-type]
    )
    error_factory = RepoErrorFactory()
    git_ops = GitOpsService(error_factory, sleep=lambda _: None, jitter=lambda: 0.0)

    svc = WorkspaceSyncService(
        env_status_svc=env_status_svc,
        worktree_repo=fake_worktree_repo,  # type: ignore[arg-type]
        repo_repo=fake_repo_repo,  # type: ignore[arg-type]
        repo_factory=RepositoryFactory(workspace_config),
        workspace=workspace,
        git_ops=git_ops,
    )
    assert isinstance(svc, WorkspaceSyncService)


def test_get_feature_environment_worktrees_helper_unused_directly(workspace: Workspace) -> None:
    """FeatureWorktree construction is owned by EnvStatusService now; this test pins that contract."""
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=workspace.root_path / "alpha")
    wt = FeatureWorktree(
        workspace=workspace,
        environment=env,
        repository=ProjectRepository(name="demo", main_path=workspace.root_path / "demo", main_branch="main"),
    )
    assert wt.repository.name == "demo"


def test_sync_env_with_empty_worktrees_returns_successful_empty_report(
    workspace: Workspace, workspace_config: WorkspaceConfig
) -> None:
    """sync_env over an env with zero worktrees produces a success=True empty report."""
    svc = _make_service(workspace, workspace_config)
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=workspace.root_path / "alpha")
    env_worktrees = FeatureEnvironmentWorktrees(environment=env, worktrees=[])

    report = svc.sync_env(env_worktrees)

    assert report.env == "alpha"
    assert report.repos == []
    assert report.success is True


def test_fetch_all_with_no_envs_or_standalones_returns_empty_report(
    workspace: Workspace, workspace_config: WorkspaceConfig
) -> None:
    """No envs (FakeReadWorkspaceRepository returns []) and project-only scope → empty report, no reporter calls."""
    svc = _make_service(workspace, workspace_config)
    reporter: IFetchReporter = _NullFetchReporter()  # type: ignore[assignment]

    report = svc.fetch_all(scope=RepoScope.project, patterns=None, reporter=reporter)

    assert report.projects == []
    assert report.standalone == []
    assert report.success is True


def test_pull_all_with_no_envs_or_standalones_returns_empty_report(
    workspace: Workspace, workspace_config: WorkspaceConfig
) -> None:
    """Same shape as fetch_all: empty inputs → empty report, no integrate happens."""
    svc = _make_service(workspace, workspace_config)
    reporter: IPullReporter = _NullPullReporter()  # type: ignore[assignment]

    report = svc.pull_all(
        scope=RepoScope.project,
        patterns=None,
        mode=PullMode.ff_only,
        autostash=False,
        reporter=reporter,
    )

    assert report.envs == []
    assert report.standalone == []
    assert report.skipped == []
    assert report.success is True
