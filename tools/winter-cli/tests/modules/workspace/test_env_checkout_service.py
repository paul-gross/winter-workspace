from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from winter_cli.modules.workspace.env_checkout_service import EnvCheckoutService
from winter_cli.modules.workspace.models import (
    CheckoutResult,
    FeatureEnvironment,
    FeatureEnvironmentWorktrees,
    FeatureWorktree,
    ProjectRepository,
    Workspace,
)

WORKSPACE_ROOT = Path("/ws")


@pytest.fixture
def workspace() -> Workspace:
    return Workspace(root_path=WORKSPACE_ROOT, session_prefix="t", main_branch="main")


class FakeWriteRepoRepository:
    """Stub for the `IWriteRepoRepository` Protocol — records every call.

    `repos_without_local_ref`, `dirty_worktree_repos`, and
    `repos_with_commits_not_in` are pre-seeded by the test before the call;
    each query method returns True iff the worktree's repo name is in the set.
    """

    def __init__(self) -> None:
        self.set_upstream_calls: list[tuple[str, str]] = []
        self.set_push_default_calls: list[str] = []
        self.unset_upstream_calls: list[str] = []
        self.hard_reset_calls: list[tuple[str, str]] = []
        self.repos_without_local_ref: set[str] = set()
        self.dirty_worktree_repos: set[str] = set()
        self.repos_with_commits_not_in: set[str] = set()

    def set_upstream(self, worktree: FeatureWorktree, upstream: str) -> None:
        self.set_upstream_calls.append((worktree.repository.name, upstream))

    def set_push_default(self, worktree: FeatureWorktree) -> None:
        self.set_push_default_calls.append(worktree.repository.name)

    def unset_upstream(self, worktree: FeatureWorktree) -> None:
        self.unset_upstream_calls.append(worktree.repository.name)

    def has_local_ref(self, worktree: FeatureWorktree, ref: str) -> bool:
        return worktree.repository.name not in self.repos_without_local_ref

    def is_worktree_dirty(self, worktree: FeatureWorktree) -> bool:
        return worktree.repository.name in self.dirty_worktree_repos

    def count_commits_not_in(self, worktree: FeatureWorktree, ref: str) -> int:
        return 1 if worktree.repository.name in self.repos_with_commits_not_in else 0

    def hard_reset(self, worktree: FeatureWorktree, ref: str) -> None:
        self.hard_reset_calls.append((worktree.repository.name, ref))

    # Methods touched by other EnvCheckoutService code paths — raise to surface
    # accidental fan-out beyond the call under test.
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"FakeWriteRepoRepository.{name} called unexpectedly")


@pytest.fixture
def fake_repo_repo() -> FakeWriteRepoRepository:
    return FakeWriteRepoRepository()


@pytest.fixture
def service(fake_repo_repo: FakeWriteRepoRepository) -> EnvCheckoutService:
    return EnvCheckoutService(repo_repo=fake_repo_repo)  # type: ignore[arg-type]


def _env_worktrees(workspace: Workspace, repos: list[ProjectRepository]) -> FeatureEnvironmentWorktrees:
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=workspace.root_path / "alpha")
    worktrees = [FeatureWorktree(workspace=workspace, environment=env, repository=r) for r in repos]
    return FeatureEnvironmentWorktrees(environment=env, worktrees=worktrees)


def test_connect_env_sets_upstream_for_non_pinned(
    workspace: Workspace, service: EnvCheckoutService, fake_repo_repo: FakeWriteRepoRepository
) -> None:
    """`connect_env` invokes `set_upstream(origin/<feature>) + set_push_default` per non-pinned worktree."""
    repos = [
        ProjectRepository(name="feature-repo", main_path=workspace.root_path / "feature-repo", main_branch="main"),
        ProjectRepository(
            name="pinned-repo", main_path=workspace.root_path / "pinned-repo", main_branch="main", pinned=True
        ),
    ]
    env_wts = _env_worktrees(workspace, repos)

    count = service.connect_env(env_wts, feature_branch="feature/widget")

    assert count == 1
    assert fake_repo_repo.set_upstream_calls == [("feature-repo", "origin/feature/widget")]
    assert fake_repo_repo.set_push_default_calls == ["feature-repo"]


def test_disconnect_env_skips_pinned_and_unsets_others(
    workspace: Workspace, service: EnvCheckoutService, fake_repo_repo: FakeWriteRepoRepository
) -> None:
    repos = [
        ProjectRepository(name="feature-repo", main_path=workspace.root_path / "feature-repo", main_branch="main"),
        ProjectRepository(
            name="pinned-repo", main_path=workspace.root_path / "pinned-repo", main_branch="main", pinned=True
        ),
    ]
    env_wts = _env_worktrees(workspace, repos)

    count = service.disconnect_env(env_wts)

    assert count == 1
    assert fake_repo_repo.unset_upstream_calls == ["feature-repo"]


def test_checkout_env_resets_clean_repos_with_present_ref(
    workspace: Workspace, service: EnvCheckoutService, fake_repo_repo: FakeWriteRepoRepository
) -> None:
    """Phase 1 passes for all repos → Phase 2 wires upstream + hard-resets each."""
    repos = [
        ProjectRepository(name="r1", main_path=workspace.root_path / "r1", main_branch="main"),
        ProjectRepository(name="r2", main_path=workspace.root_path / "r2", main_branch="main"),
    ]
    env_wts = _env_worktrees(workspace, repos)

    report = service.checkout_env(env_wts, feature_branch="feature/widget", force=False)

    assert report.aborted is False
    assert [(o.repo_name, o.result) for o in report.repos] == [
        ("r1", CheckoutResult.reset),
        ("r2", CheckoutResult.reset),
    ]
    assert fake_repo_repo.hard_reset_calls == [("r1", "origin/feature/widget"), ("r2", "origin/feature/widget")]
    assert fake_repo_repo.set_upstream_calls == [
        ("r1", "origin/feature/widget"),
        ("r2", "origin/feature/widget"),
    ]


def test_checkout_env_aborts_whole_env_when_any_repo_is_dirty_without_force(
    workspace: Workspace, service: EnvCheckoutService, fake_repo_repo: FakeWriteRepoRepository
) -> None:
    """One dirty repo + force=False → no `hard_reset` runs in ANY repo (all-or-nothing safety)."""
    repos = [
        ProjectRepository(name="clean-repo", main_path=workspace.root_path / "clean-repo", main_branch="main"),
        ProjectRepository(name="dirty-repo", main_path=workspace.root_path / "dirty-repo", main_branch="main"),
    ]
    fake_repo_repo.dirty_worktree_repos.add("dirty-repo")
    env_wts = _env_worktrees(workspace, repos)

    report = service.checkout_env(env_wts, feature_branch="feature/widget", force=False)

    assert report.aborted is True
    refused = [o for o in report.repos if o.result == CheckoutResult.refused_dirty]
    assert [o.repo_name for o in refused] == ["dirty-repo"]
    # The clean repo is not in the refused list and Phase 2 never runs.
    assert fake_repo_repo.hard_reset_calls == []
    assert fake_repo_repo.set_upstream_calls == []


def test_checkout_env_with_force_resets_dirty_repos(
    workspace: Workspace, service: EnvCheckoutService, fake_repo_repo: FakeWriteRepoRepository
) -> None:
    """`force=True` skips both dirty and divergent gates; Phase 2 runs for every repo."""
    repos = [
        ProjectRepository(name="dirty-repo", main_path=workspace.root_path / "dirty-repo", main_branch="main"),
    ]
    fake_repo_repo.dirty_worktree_repos.add("dirty-repo")
    env_wts = _env_worktrees(workspace, repos)

    report = service.checkout_env(env_wts, feature_branch="feature/widget", force=True)

    assert report.aborted is False
    assert [(o.repo_name, o.result) for o in report.repos] == [("dirty-repo", CheckoutResult.reset)]
    assert fake_repo_repo.hard_reset_calls == [("dirty-repo", "origin/feature/widget")]
