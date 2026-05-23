from __future__ import annotations

import concurrent.futures
import dataclasses
import logging

import click

from winter_cli.modules.workspace.env_status_service import EnvStatusService
from winter_cli.modules.workspace.fetch_reporter import IFetchReporter
from winter_cli.modules.workspace.internal.git_ops_service import GitOpsService
from winter_cli.modules.workspace.models import (
    EnvSkipped,
    EnvSyncReport,
    FeatureEnvironment,
    FeatureEnvironmentWorktrees,
    FeatureWorktree,
    FetchReport,
    ProjectRepository,
    PullMode,
    PullReport,
    RepoError,
    RepoFetchOutcome,
    RepoScope,
    RepoSyncOutcome,
    StandaloneRepository,
    SyncResult,
    Workspace,
)
from winter_cli.modules.workspace.pattern_match import matches_any_pattern
from winter_cli.modules.workspace.pull_reporter import IPullReporter
from winter_cli.modules.workspace.repo_repository import IWriteRepoRepository
from winter_cli.modules.workspace.repository_factory import RepositoryFactory
from winter_cli.modules.workspace.workspace_repository import IReadWorkspaceRepository

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _PullTarget:
    """Per-worktree integration target resolved up-front for fan-out."""

    env_name: str
    worktree: FeatureWorktree
    target_ref: str


class WorkspaceSyncService:
    """Network-touching git operations across envs and standalone repos.

    Owns `sync_env` (single env, ff-or-merge against `origin/<main>`),
    `fetch_all`, `pull_all`, `push_all`. Parallelism is bounded by the shared
    `GitOpsService` executor so a wide workspace doesn't overwhelm SSH.
    """

    def __init__(
        self,
        env_status_svc: EnvStatusService,
        worktree_repo: IReadWorkspaceRepository,
        repo_repo: IWriteRepoRepository,
        repo_factory: RepositoryFactory,
        workspace: Workspace,
        git_ops: GitOpsService,
    ) -> None:
        self._env_status_svc = env_status_svc
        self._worktree_repo = worktree_repo
        self._repo_repo = repo_repo
        self._repo_factory = repo_factory
        self._workspace = workspace
        self._git_ops = git_ops

    def sync_env(self, env_worktrees: FeatureEnvironmentWorktrees) -> EnvSyncReport:
        """Sync a worktree's repos against `origin/<main>` (ff-or-merge).

        Sync intentionally falls back to a merge commit when ff-only fails —
        this keeps source-checkout fast-forwards aligned with the worktree even
        when the worktree has drifted. Use `winter ws pull` for the ff-only
        flow against the feature branch.
        """
        worktrees = env_worktrees.worktrees
        self._fetch_in_parallel(worktrees)

        outcomes = self._integrate_in_parallel(
            [(wt, f"origin/{wt.repository.main_branch}") for wt in worktrees],
            mode=PullMode.merge,
            autostash=False,
        )
        outcomes = self._sort_outcomes(outcomes, [wt.repository.name for wt in worktrees])

        project_repos = [wt.repository for wt in worktrees]
        with self._git_ops.executor() as pool:
            list(pool.map(self._repo_repo.sync_ff_only, project_repos))

        success = all(o.sync_result != SyncResult.diverged for o in outcomes)
        return EnvSyncReport(env=env_worktrees.environment.name, repos=outcomes, success=success)

    def fetch_all(
        self,
        scope: RepoScope,
        patterns: list[str] | None,
        reporter: IFetchReporter,
    ) -> FetchReport:
        """Fetch unique project repos matched by `patterns`, and/or standalone repos.

        `patterns` filters project worktrees by segment-aware glob over
        `<env>/<repo>` (empty list ⇒ `*/*`); any matching worktree pulls its
        project repo into the fetch set. Worktrees of a project repo share
        a `.git`, so one `git fetch origin` updates remote refs for every
        env — we run that fetch from any one of the matching worktrees and
        emit a single `[project/<repo>]` event for it. Standalone repos are
        independent clones, fetched per-repo. Events fire in completion order.
        """
        patterns = patterns or ["*/*"]
        project_repos = self._repo_factory.get_project_repos()
        envs = self._select_envs(scope, project_repos)
        standalone_repos = self._repo_factory.get_standalone_repos() if scope.includes_standalone else []

        env_worktrees_by_env = self._build_env_worktrees_map(envs, project_repos)
        matched_by_env: dict[str, list[FeatureWorktree]] = {
            env.name: [
                wt
                for wt in env_worktrees_by_env[env.name].worktrees
                if matches_any_pattern(env.name, wt.repository.name, patterns)
            ]
            for env in envs
        }
        matched_envs = [env for env in envs if matched_by_env[env.name]]
        all_worktrees: list[tuple[str, FeatureWorktree]] = [
            (env.name, wt) for env in matched_envs for wt in matched_by_env[env.name]
        ]

        all_worktrees = self._drop_missing_worktrees(all_worktrees)
        standalone_repos = self._drop_missing_standalones(standalone_repos)

        # Pick one representative worktree per unique project repo — the
        # source `.git` is shared, so any of them works. Insertion order is
        # preserved by the dict so output ordering stays stable when fetches
        # complete in deterministic order (rare; see as_completed below).
        repo_reps: dict[str, FeatureWorktree] = {}
        for _, wt in all_worktrees:
            repo_reps.setdefault(wt.repository.name, wt)

        if not repo_reps and not standalone_repos:
            return FetchReport(projects=[], standalone=[])

        reporter.fetch_started()

        project_results: list[RepoFetchOutcome] = []
        standalone_results: list[RepoFetchOutcome] = []

        with self._git_ops.executor() as pool:
            future_keys: dict[concurrent.futures.Future, tuple[str, str]] = {}
            for repo_name, wt in repo_reps.items():
                fut = pool.submit(self._repo_repo.fetch, wt)
                future_keys[fut] = ("project", repo_name)
            for repo in standalone_repos:
                fut = pool.submit(self._repo_repo.fetch_standalone, repo)
                future_keys[fut] = ("standalone", repo.name)

            for fut in concurrent.futures.as_completed(future_keys):
                scope_label, repo_name = future_keys[fut]
                outcome = self._collect_fetch(fut, repo_name)
                reporter.repo_fetched(scope_label, repo_name, outcome.success, outcome.error)
                if scope_label == "project":
                    project_results.append(outcome)
                else:
                    standalone_results.append(outcome)

        project_results.sort(key=lambda o: list(repo_reps).index(o.repo_name))
        standalone_results.sort(key=lambda o: o.repo_name)
        report = FetchReport(projects=project_results, standalone=standalone_results)
        reporter.fetch_completed(report.success)
        return report

    def pull_all(
        self,
        scope: RepoScope,
        patterns: list[str] | None,
        mode: PullMode,
        autostash: bool,
        reporter: IPullReporter,
    ) -> PullReport:
        """Fetch + integrate (ff-only / merge / rebase) project worktrees matched
        by `patterns`, and/or standalone repos.

        `patterns` filters project worktrees by segment-aware glob over
        `<env>/<repo>` (empty list ⇒ `*/*`). Pinned worktrees integrate from
        `origin/<main_branch>`; non-pinned integrate from
        `origin/<feature_branch>` when the env is connected and from
        `origin/<main_branch>` otherwise; standalone repos integrate from
        their tracked upstream. Per-repo events fire on `reporter` as each
        integrate finishes, in completion order.
        """
        patterns = patterns or ["*/*"]
        project_repos = self._repo_factory.get_project_repos()
        envs = self._select_envs(scope, project_repos)
        standalone_repos = self._repo_factory.get_standalone_repos() if scope.includes_standalone else []
        env_worktrees_by_env = self._build_env_worktrees_map(envs, project_repos)

        matched_by_env: dict[str, list[FeatureWorktree]] = {
            env.name: [
                wt
                for wt in env_worktrees_by_env[env.name].worktrees
                if matches_any_pattern(env.name, wt.repository.name, patterns)
            ]
            for env in envs
        }
        matched_envs = [env for env in envs if matched_by_env[env.name]]

        targets, skipped = self._build_pull_targets(matched_envs, matched_by_env, project_repos)
        targets = [
            t
            for t in targets
            if self._warn_unless_present(t.worktree.path, f"{t.env_name}/{t.worktree.repository.name}", t.env_name)
        ]
        standalone_repos = self._drop_missing_standalones(standalone_repos)

        if not targets and not standalone_repos and not skipped:
            return PullReport(envs=[], standalone=[], skipped=[])

        reporter.pull_started()

        # Surface env-level skips up front so the stream reads as: phase header →
        # skips → per-repo results → summary. The pinned worktrees in a skipped
        # env still flow through the integrate stage below.
        for skip in skipped:
            reporter.env_skipped(skip.env, skip.reason)

        # Group integrate targets by source repo so each project repo gets
        # one shared fetch. Within a group, integrates run serially (they're
        # local-only and fast); across groups they run in parallel up to the
        # pool's slot count. A slow fetch only blocks its own group's slot.
        # Fetch errors are logged but don't abort: stale local refs just
        # produce up-to-date / diverged outcomes from the integrate.
        targets_by_repo: dict[str, list[_PullTarget]] = {}
        for t in targets:
            targets_by_repo.setdefault(t.worktree.repository.name, []).append(t)

        outcomes_by_env: dict[str, list[RepoSyncOutcome]] = {env.name: [] for env in matched_envs}
        standalone_outcomes: list[RepoSyncOutcome] = []

        with self._git_ops.executor() as pool:
            project_futures: dict[concurrent.futures.Future, str] = {}
            standalone_futures: dict[concurrent.futures.Future, str] = {}
            for repo_name, group in targets_by_repo.items():
                fut = pool.submit(
                    self._fetch_then_integrate_group,
                    group,
                    mode,
                    autostash,
                    reporter,
                )
                project_futures[fut] = repo_name
            for repo in standalone_repos:
                fut = pool.submit(
                    self._fetch_then_integrate_standalone,
                    repo,
                    mode,
                    autostash,
                )
                standalone_futures[fut] = repo.name

            for fut in concurrent.futures.as_completed({**project_futures, **standalone_futures}):
                if fut in project_futures:
                    # Group task already emitted per-worktree events itself —
                    # we just collect outcomes for the final report.
                    for env_name_, outcome in fut.result():
                        outcomes_by_env[env_name_].append(outcome)
                else:
                    outcome = fut.result()
                    reporter.repo_synced(
                        "standalone",
                        outcome.repo_name,
                        outcome.sync_result,
                        outcome.ahead,
                        outcome.behind,
                    )
                    standalone_outcomes.append(outcome)

        env_reports: list[EnvSyncReport] = []
        for env in matched_envs:
            if not outcomes_by_env[env.name]:
                continue
            repo_order = [t.worktree.repository.name for t in targets if t.env_name == env.name]
            env_outcomes = self._sort_outcomes(outcomes_by_env[env.name], repo_order)
            success = all(o.sync_result != SyncResult.diverged for o in env_outcomes)
            env_reports.append(EnvSyncReport(env=env.name, repos=env_outcomes, success=success))

        standalone_outcomes.sort(key=lambda o: o.repo_name)
        report = PullReport(envs=env_reports, standalone=standalone_outcomes, skipped=skipped)
        reporter.pull_completed(report.success)
        return report

    def _build_pull_targets(
        self,
        envs: list[FeatureEnvironment],
        matched_by_env: dict[str, list[FeatureWorktree]],
        project_repos: list[ProjectRepository],
    ) -> tuple[list[_PullTarget], list[EnvSkipped]]:
        """Resolve per-worktree pull targets.

        Each worktree pulls from its own ref independently — no env-level
        skip. Pinned worktrees always pull from `origin/<main_branch>`;
        non-pinned worktrees pull from `origin/<feature_branch>` when the
        env is connected, otherwise they fall back to `origin/<main_branch>`
        too. Worktrees missing from disk are filtered out by
        `_drop_missing_worktrees` in the caller, so an env that only has
        pinned worktrees materialized produces no events for the unborn
        non-pinned ones.

        A non-pinned worktree with local feature commits and no feature
        branch will see a `diverged` integrate outcome — that's the right
        signal; it surfaces just as clearly as the old "not connected"
        skip message did, without blocking the fresh-env / partial-init
        case where pulling from main is exactly what the user wants.
        """
        targets: list[_PullTarget] = []
        for env in envs:
            env_status = self._worktree_repo.get_environment_status(env, project_repos)
            for wt in matched_by_env[env.name]:
                if wt.repository.pinned or not env_status.feature_branch:
                    target_ref = f"origin/{wt.repository.main_branch}"
                else:
                    target_ref = f"origin/{env_status.feature_branch}"
                targets.append(_PullTarget(env_name=env.name, worktree=wt, target_ref=target_ref))
        return targets, []

    def _build_env_worktrees_map(
        self,
        envs: list[FeatureEnvironment],
        project_repos: list[ProjectRepository],
    ) -> dict[str, FeatureEnvironmentWorktrees]:
        return {env.name: self._env_status_svc.get_feature_environment_worktrees(env, project_repos) for env in envs}

    def _fetch_in_parallel(
        self,
        worktrees: list[FeatureWorktree],
        log_errors: bool = False,
    ) -> None:
        if not worktrees:
            return
        with self._git_ops.executor() as pool:
            futures = {pool.submit(self._repo_repo.fetch, wt): wt for wt in worktrees}
            for fut, wt in futures.items():
                try:
                    fut.result()
                except RepoError as exc:
                    if log_errors:
                        logger.warning("Fetch failed for %s: %s", wt.repository.name, exc)
                    else:
                        raise

    @staticmethod
    def _warn_unless_present(path, label: str, init_target: str | None) -> bool:
        """Return True if `path` exists; otherwise warn the user and return False.

        Surfaces newly-added config entries whose worktrees / clones haven't
        been provisioned yet — happens when a repo is added to
        `.winter/config.toml` but `winter ws init` hasn't been re-run.
        """
        if path.exists():
            return True
        fix = f"winter ws init {init_target}" if init_target else "winter ws init"
        click.echo(f"warning: {label} — missing on disk (run `{fix}`)", err=True)
        return False

    def _drop_missing_worktrees(
        self,
        items: list[tuple[str, FeatureWorktree]],
    ) -> list[tuple[str, FeatureWorktree]]:
        return [
            (env_name, wt)
            for (env_name, wt) in items
            if self._warn_unless_present(wt.path, f"{env_name}/{wt.repository.name}", env_name)
        ]

    def _drop_missing_standalones(
        self,
        repos: list[StandaloneRepository],
    ) -> list[StandaloneRepository]:
        return [r for r in repos if self._warn_unless_present(r.path, f"standalone/{r.name}", None)]

    def _fetch_then_integrate_group(
        self,
        targets: list[_PullTarget],
        mode: PullMode,
        autostash: bool,
        reporter: IPullReporter,
    ) -> list[tuple[str, RepoSyncOutcome]]:
        """Fetch a project repo once, then integrate each of its worktrees.

        Worktrees of a project repo share a `.git`, so a single
        `git fetch origin` from any of them updates remote refs for every
        worktree — we fetch from the first and run integrate sequentially
        for the rest. Per-worktree integrate events are emitted on
        `reporter` from inside this task so the user sees them as soon as
        each integrate lands, even within the same group.
        """
        first_wt = targets[0].worktree
        try:
            self._repo_repo.fetch(first_wt)
        except RepoError as exc:
            logger.warning("Fetch failed for %s: %s", first_wt.repository.name, exc)
        results: list[tuple[str, RepoSyncOutcome]] = []
        for t in targets:
            outcome = self._repo_repo.integrate(t.worktree, t.target_ref, mode, autostash)
            reporter.repo_synced(
                t.env_name,
                outcome.repo_name,
                outcome.sync_result,
                outcome.ahead,
                outcome.behind,
            )
            results.append((t.env_name, outcome))
        return results

    def _fetch_then_integrate_standalone(
        self,
        repo: StandaloneRepository,
        mode: PullMode,
        autostash: bool,
    ) -> RepoSyncOutcome:
        try:
            self._repo_repo.fetch_standalone(repo)
        except RepoError as exc:
            logger.warning("Fetch failed for standalone %s: %s", repo.name, exc)
        return self._repo_repo.integrate_standalone(repo, mode, autostash)

    def _integrate_in_parallel(
        self,
        targets: list[tuple[FeatureWorktree, str]],
        mode: PullMode,
        autostash: bool,
    ) -> list[RepoSyncOutcome]:
        if not targets:
            return []
        results: list[RepoSyncOutcome | None] = [None] * len(targets)
        with self._git_ops.executor() as pool:
            futures = {
                pool.submit(self._repo_repo.integrate, wt, target_ref, mode, autostash): idx
                for idx, (wt, target_ref) in enumerate(targets)
            }
            for fut, idx in futures.items():
                results[idx] = fut.result()
        return [r for r in results if r is not None]

    @staticmethod
    def _sort_outcomes(outcomes: list[RepoSyncOutcome], repo_order: list[str]) -> list[RepoSyncOutcome]:
        return sorted(outcomes, key=lambda o: repo_order.index(o.repo_name))

    def _select_envs(
        self,
        scope: RepoScope,
        project_repos: list[ProjectRepository],
    ) -> list[FeatureEnvironment]:
        """Resolve envs to operate on based on scope.

        Returns no envs when scope excludes project repos (e.g. --standalone).
        Pattern filtering happens at the worktree level in the caller.
        """
        if not scope.includes_project:
            return []
        return self._worktree_repo.get_environments(self._workspace, project_repos)

    @staticmethod
    def _collect_fetch(fut: concurrent.futures.Future, repo_name: str) -> RepoFetchOutcome:
        try:
            fut.result()
            return RepoFetchOutcome(repo_name=repo_name, success=True)
        except RepoError as exc:
            return RepoFetchOutcome(repo_name=repo_name, success=False, error=str(exc))
