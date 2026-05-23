from __future__ import annotations

import logging

from winter_cli.modules.workspace.env_status_service import EnvStatusService
from winter_cli.modules.workspace.models import (
    EnvPushReport,
    EnvSkipped,
    FeatureWorktree,
    PinnedScope,
    PushReport,
    RepoError,
    RepoPushOutcome,
    RepoScope,
    StandaloneRepository,
    Workspace,
)
from winter_cli.modules.workspace.pattern_match import matches_any_pattern
from winter_cli.modules.workspace.repo_repository import IWriteRepoRepository
from winter_cli.modules.workspace.repository_factory import RepositoryFactory
from winter_cli.modules.workspace.workspace_repository import IReadWorkspaceRepository

logger = logging.getLogger(__name__)


class WorkspacePushService:
    """Pushes project worktrees and/or standalone repos with commits ahead of upstream.

    Pulled out of WorkspaceSyncService so each sync-vs-push concern has its
    own bounded surface. Both services share `pattern_match.matches_any_pattern`
    for the segment-aware `<env>/<repo>` glob.
    """

    def __init__(
        self,
        env_status_svc: EnvStatusService,
        worktree_repo: IReadWorkspaceRepository,
        repo_repo: IWriteRepoRepository,
        repo_factory: RepositoryFactory,
        workspace: Workspace,
    ) -> None:
        self._env_status_svc = env_status_svc
        self._worktree_repo = worktree_repo
        self._repo_repo = repo_repo
        self._repo_factory = repo_factory
        self._workspace = workspace

    def push_all(
        self,
        scope: RepoScope,
        patterns: list[str] | None = None,
        pinned_scope: PinnedScope = PinnedScope.exclude,
    ) -> PushReport:
        """Push project worktrees matched by `patterns`, and/or standalone repos.

        `patterns` filters project worktrees by segment-aware glob over
        `<env>/<repo>` (empty list ⇒ `*/*`). `pinned_scope` controls whether
        pinned worktrees are included, excluded (default), or pushed alone.
        Non-pinned worktrees push HEAD:refs/heads/<feature_branch>; pinned
        worktrees plain-push to whatever their local branch tracks. Standalone
        repos plain-push to their tracked upstream and ignore `patterns`. Only
        repos with commits ahead of upstream are pushed.
        """
        patterns = patterns or ["*/*"]
        project_repos = self._repo_factory.get_project_repos()
        envs = self._worktree_repo.get_environments(self._workspace, project_repos) if scope.includes_project else []
        standalone_repos = self._repo_factory.get_standalone_repos() if scope.includes_standalone else []

        env_reports: list[EnvPushReport] = []
        skipped: list[EnvSkipped] = []
        for env in envs:
            env_status = self._worktree_repo.get_environment_status(env, project_repos)
            env_worktrees = self._env_status_svc.get_feature_environment_worktrees(env, project_repos)

            worktrees = [
                wt
                for wt in env_worktrees.worktrees
                if self._matches_pinned_scope(wt, pinned_scope)
                and matches_any_pattern(env.name, wt.repository.name, patterns)
            ]
            if not worktrees:
                continue

            non_pinned = [wt for wt in worktrees if not wt.repository.pinned]
            if non_pinned and not env_status.feature_branch:
                skipped.append(
                    EnvSkipped(
                        env=env.name,
                        reason="not connected — run `winter ws connect` first",
                    )
                )
                worktrees = [wt for wt in worktrees if wt.repository.pinned]

            outcomes = [
                self._push_one(wt, env_status.feature_branch) for wt in worktrees if self._has_commits_to_push(wt)
            ]
            env_reports.append(EnvPushReport(env=env.name, repos=outcomes))

        standalone_outcomes: list[RepoPushOutcome] = []
        for repo in standalone_repos:
            if self._repo_repo.get_standalone_upstream(repo) is None:
                standalone_outcomes.append(
                    RepoPushOutcome(
                        repo_name=repo.name,
                        pushed=False,
                        error="no upstream — set one with `git branch --set-upstream-to`",
                    )
                )
                continue
            if self._repo_repo.get_standalone_tracking_ahead(repo) == 0:
                continue
            standalone_outcomes.append(self._push_one_standalone(repo))

        return PushReport(envs=env_reports, standalone=standalone_outcomes, skipped=skipped)

    def _has_commits_to_push(self, wt: FeatureWorktree) -> bool:
        status = self._repo_repo.get_worktree_status(wt)
        if wt.repository.pinned:
            return status.tracking_ahead > 0
        return status.tracking_ahead > 0 or status.ahead > 0

    @staticmethod
    def _matches_pinned_scope(wt: FeatureWorktree, pinned_scope: PinnedScope) -> bool:
        if wt.repository.pinned:
            return pinned_scope.matches_pinned
        return pinned_scope.matches_non_pinned

    def _push_one(self, wt: FeatureWorktree, feature_branch: str | None) -> RepoPushOutcome:
        target_branch = None if wt.repository.pinned else feature_branch
        try:
            commits = self._repo_repo.push(wt, target_branch)
        except RepoError as exc:
            logger.warning("Push failed for %s: %s", wt.repository.name, exc)
            return RepoPushOutcome(repo_name=wt.repository.name, pushed=False, error=str(exc))
        return RepoPushOutcome(repo_name=wt.repository.name, pushed=True, commits=commits)

    def _push_one_standalone(self, repo: StandaloneRepository) -> RepoPushOutcome:
        try:
            commits = self._repo_repo.push_standalone(repo)
        except RepoError as exc:
            logger.warning("Push failed for standalone %s: %s", repo.name, exc)
            return RepoPushOutcome(repo_name=repo.name, pushed=False, error=str(exc))
        return RepoPushOutcome(repo_name=repo.name, pushed=True, commits=commits)
