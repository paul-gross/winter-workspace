from __future__ import annotations

import threading
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
    RepoError,
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
    because `fetch_all` fetches + fast-forwards each matched source repo
    through it. The empty-input tests below never reach that fan-out, but
    keeping it a no-op (instead of letting `__getattr__` raise) documents the
    accessor `fetch_all` uses. Other attribute accesses still raise so
    accidental fan-out trips the test.
    """

    def sync_ff_only(self, repo: ProjectRepository) -> int:
        return 0

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"FakeWriteRepoRepository.{name} called unexpectedly")


class _NullFetchReporter:
    def fetch_started(self) -> None:
        return None

    def repo_fetched(self, scope: str, repo: str, success: bool, commits: int, error: str | None) -> None:
        return None

    def fetch_completed(self, success: bool) -> None:
        return None


class _NullPullReporter:
    def pull_started(self) -> None:
        return None

    def env_skipped(self, env: str, reason: str) -> None:
        return None

    def repo_synced(self, scope: str, repo: str, result: Any, commits: int, ahead: int, behind: int) -> None:
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


class _SpyWriteRepoRepository:
    """Records `sync_ff_only` calls and fails loudly if `fetch` is used.

    Pins `fetch_all`'s contract: it refreshes + fast-forwards each project repo
    through `sync_ff_only` against the source checkout, never a per-worktree
    `fetch`. `raise_on` names a repo whose `sync_ff_only` raises, modelling a
    diverged source main.
    """

    def __init__(self, raise_on: str | None = None, commits: int = 0) -> None:
        self.synced: list[ProjectRepository] = []
        self._raise_on = raise_on
        self._commits = commits
        self._lock = threading.Lock()

    def sync_ff_only(self, repo: ProjectRepository) -> int:
        with self._lock:
            self.synced.append(repo)
        if repo.name == self._raise_on:
            raise RepoError(f"sync_ff_only failed for {repo.name}", cwd=str(repo.main_path))
        return self._commits

    def fetch(self, worktree: FeatureWorktree) -> None:
        raise AssertionError("fetch_all must fast-forward via sync_ff_only, not fetch")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"_SpyWriteRepoRepository.{name} called unexpectedly")


class _FakeEnvStatusService:
    """Returns a fixed worktree set, sidestepping on-disk worktree discovery."""

    def __init__(self, env_worktrees: FeatureEnvironmentWorktrees) -> None:
        self._env_worktrees = env_worktrees

    def get_feature_environment_worktrees(
        self, env: FeatureEnvironment, project_repos: list[ProjectRepository]
    ) -> FeatureEnvironmentWorktrees:
        return self._env_worktrees


def _make_fetch_service(
    workspace: Workspace,
    workspace_config: WorkspaceConfig,
    env_worktrees: FeatureEnvironmentWorktrees,
    repo_repo: _SpyWriteRepoRepository,
) -> WorkspaceSyncService:
    class _OneEnvWorktreeRepo(FakeReadWorkspaceRepository):
        def get_environments(self, workspace_, project_repos):  # type: ignore[no-untyped-def]
            return [env_worktrees.environment]

    git_ops = GitOpsService(RepoErrorFactory(), sleep=lambda _: None, jitter=lambda: 0.0)
    return WorkspaceSyncService(
        env_status_svc=_FakeEnvStatusService(env_worktrees),  # type: ignore[arg-type]
        worktree_repo=_OneEnvWorktreeRepo(),  # type: ignore[arg-type]
        repo_repo=repo_repo,  # type: ignore[arg-type]
        repo_factory=RepositoryFactory(workspace_config),
        workspace=workspace,
        git_ops=git_ops,
    )


def _make_env_with_worktree(
    workspace: Workspace, tmp_path: Path
) -> tuple[FeatureEnvironmentWorktrees, ProjectRepository]:
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=tmp_path / "alpha")
    repo = ProjectRepository(name="demo", main_path=tmp_path / "projects" / "demo", main_branch="main")
    wt = FeatureWorktree(workspace=workspace, environment=env, repository=repo)
    wt.path.mkdir(parents=True)  # _warn_unless_present drops worktrees missing on disk
    return FeatureEnvironmentWorktrees(environment=env, worktrees=[wt]), repo


def test_fetch_all_fast_forwards_source_checkouts_via_sync_ff_only(
    workspace_config: WorkspaceConfig, tmp_path: Path
) -> None:
    """fetch_all routes each matched project repo through sync_ff_only (not fetch).

    sync_ff_only fetches the shared source-checkout `.git` and fast-forwards
    its local main; doing it here is what keeps `winter ws init`'s branch base
    current.
    """
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    env_worktrees, repo = _make_env_with_worktree(workspace, tmp_path)
    repo_repo = _SpyWriteRepoRepository()
    svc = _make_fetch_service(workspace, workspace_config, env_worktrees, repo_repo)
    reporter: IFetchReporter = _NullFetchReporter()  # type: ignore[assignment]

    report = svc.fetch_all(scope=RepoScope.project, patterns=None, reporter=reporter)

    assert [r.name for r in repo_repo.synced] == ["demo"]
    assert repo_repo.synced[0].main_path == repo.main_path
    assert [o.repo_name for o in report.projects] == ["demo"]
    assert report.success is True


def test_fetch_all_propagates_sync_ff_only_commit_count(workspace_config: WorkspaceConfig, tmp_path: Path) -> None:
    """The commit count `sync_ff_only` returns surfaces on the per-repo outcome."""
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    env_worktrees, _ = _make_env_with_worktree(workspace, tmp_path)
    repo_repo = _SpyWriteRepoRepository(commits=4)
    svc = _make_fetch_service(workspace, workspace_config, env_worktrees, repo_repo)
    reporter: IFetchReporter = _NullFetchReporter()  # type: ignore[assignment]

    report = svc.fetch_all(scope=RepoScope.project, patterns=None, reporter=reporter)

    assert [o.commits for o in report.projects] == [4]
    assert report.success is True


def test_fetch_all_reports_failure_when_source_checkout_diverges(
    workspace_config: WorkspaceConfig, tmp_path: Path
) -> None:
    """A RepoError from sync_ff_only (e.g. diverged source main) is a failed fetch."""
    workspace = Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")
    env_worktrees, _ = _make_env_with_worktree(workspace, tmp_path)
    repo_repo = _SpyWriteRepoRepository(raise_on="demo")
    svc = _make_fetch_service(workspace, workspace_config, env_worktrees, repo_repo)
    reporter: IFetchReporter = _NullFetchReporter()  # type: ignore[assignment]

    report = svc.fetch_all(scope=RepoScope.project, patterns=None, reporter=reporter)

    assert len(report.projects) == 1
    outcome = report.projects[0]
    assert outcome.repo_name == "demo"
    assert outcome.success is False
    assert outcome.error is not None
    assert report.success is False
