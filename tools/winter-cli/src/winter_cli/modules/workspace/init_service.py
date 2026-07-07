from __future__ import annotations

import logging
import os
from concurrent.futures import as_completed
from pathlib import Path

from winter_cli.config.models import WorkspaceConfig
from winter_cli.core.filesystem import IFilesystemWriter
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.workspace.agent_install import ExtensionAgentService
from winter_cli.modules.workspace.config_lock_repository import IConfigLockRepository
from winter_cli.modules.workspace.env_index import EnvIndexAllocator
from winter_cli.modules.workspace.env_index_registry import IEnvIndexRegistry
from winter_cli.modules.workspace.extension_agentsmd_service import ExtensionAgentsMdService
from winter_cli.modules.workspace.extension_exclude_service import ExtensionExcludeService
from winter_cli.modules.workspace.extension_hook_service import ExtensionHookService
from winter_cli.modules.workspace.extension_symlink_service import ExtensionSymlinkService
from winter_cli.modules.workspace.git_repository import IGitRepository
from winter_cli.modules.workspace.init_reporter import IInitReporter
from winter_cli.modules.workspace.internal.git_ops_service import GitOpsService
from winter_cli.modules.workspace.internal.managed_block import (
    GITIGNORE_BEGIN,
    GITIGNORE_END,
    replace_or_append_block,
)
from winter_cli.modules.workspace.models import (
    IWorkspaceRepository,
    ProjectRepository,
    RepoError,
    StandaloneRepository,
)
from winter_cli.modules.workspace.models.domain_model import LockEntry, RefKind
from winter_cli.modules.workspace.repository_factory import RepositoryFactory
from winter_cli.modules.workspace.workspace_skill_service import WorkspaceSkillService

logger = logging.getLogger(__name__)

TUI_SUPPRESS_ENV = {
    "CI": "1",
    "TERM": "dumb",
    "NO_COLOR": "1",
    "FORCE_COLOR": "0",
    "NPM_CONFIG_PROGRESS": "false",
    "PNPM_PROGRESS": "false",
    "PYTHONUNBUFFERED": "1",
    "PIP_PROGRESS_BAR": "off",
    "DOTNET_NOLOGO": "1",
    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    "MISE_QUIET": "true",
}


class InitService:
    """Idempotent reconcile for source checkouts, standalone repos, and feature worktrees.

    Every operation is designed to be a no-op when the target already matches the
    config, so repeated runs are safe. Each run reapplies git identity, git-exclude
    entries, and setup commands — these are the knobs that drift most often between
    config edits.

    Error-handling shape: each per-repo task and each workspace-level step has one
    wrap-site that catches `(RepoError, OSError)` and routes the failure through
    the reporter. Leaves either return their result or raise. The public reconcile
    entrypoints are aggregators — they collect per-step booleans and never `try`.
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        repo_factory: RepositoryFactory,
        extension_symlink_svc: ExtensionSymlinkService,
        extension_hook_svc: ExtensionHookService,
        extension_exclude_svc: ExtensionExcludeService,
        extension_agentsmd_svc: ExtensionAgentsMdService,
        fs: IFilesystemWriter,
        subprocess_runner: ISubprocessRunner,
        git_repo: IGitRepository,
        git_ops: GitOpsService,
        registry: IEnvIndexRegistry,
        config_lock_repo: IConfigLockRepository | None = None,
        workspace_skill_svc: WorkspaceSkillService | None = None,
        extension_agent_svc: ExtensionAgentService | None = None,
    ) -> None:
        self._config = config
        self._repo_factory = repo_factory
        self._extension_symlink_svc = extension_symlink_svc
        self._extension_hook_svc = extension_hook_svc
        self._extension_exclude_svc = extension_exclude_svc
        self._extension_agentsmd_svc = extension_agentsmd_svc
        self._fs = fs
        self._subprocess = subprocess_runner
        self._git_repo = git_repo
        self._git_ops = git_ops
        self._config_lock_repo = config_lock_repo
        self._workspace_skill_svc = workspace_skill_svc
        self._extension_agent_svc = extension_agent_svc
        self._registry = registry

    # ── Public API ────────────────────────────────────────────────────────

    def reconcile_projects(self, reporter: IInitReporter) -> bool:
        target = "projects/"
        reporter.target_started(target)

        projects_dir = self._config.workspace_root / "projects"
        self._fs.mkdir(projects_dir, parents=True, exist_ok=True)

        success = self._write_workspace_self_exclude("projects", reporter)

        # Workspace-scope artifacts: keep the runtime log dir out of the workspace repo.
        if not self._write_workspace_artifact_excludes(reporter):
            success = False

        repos = self._repo_factory.get_project_repos()
        if not self._run_per_repo(repos, lambda r: self._reconcile_source_checkout(r, reporter)):
            success = False

        if self._workspace_skill_svc is not None and not self._workspace_skill_svc.reconcile(reporter):
            success = False

        reporter.target_completed(target, success)
        return success

    def reconcile_standalones(self, reporter: IInitReporter) -> bool:
        repos = self._repo_factory.get_standalone_repos()
        if not repos:
            return True

        target = "standalone/"
        reporter.target_started(target)

        success = self._run_per_repo(repos, lambda r: self._reconcile_standalone(r, reporter))

        # Aggregate-update workspace CLAUDE.md and `.git/info/exclude` from all
        # standalones that were successfully reconciled (i.e. exist on disk now).
        # Per-repo reconcile may have failed for some, but cloned-and-present
        # extensions still belong in both managed sections.
        present_repos = [r for r in repos if self._fs.exists(r.path)]
        if not self._extension_agentsmd_svc.finalize_agentsmd(present_repos, reporter):
            success = False
        if not self._extension_exclude_svc.finalize_excludes(present_repos, reporter):
            success = False
        if self._extension_agent_svc is not None:
            self._extension_agent_svc.check_unknown_overrides(present_repos, reporter)

        reporter.target_completed(target, success)
        return success

    def reconcile_env(self, name: str, reporter: IInitReporter) -> bool:
        reporter.target_started(name)
        success = True

        env_root = self._config.workspace_root / name
        self._fs.mkdir(env_root, parents=True, exist_ok=True)

        # Allocate and persist the env index so EnvProvisionerService can read a
        # stable, collision-free index on every subsequent call to compute(name).
        # Env files are no longer written here — env is injected at runtime.
        EnvIndexAllocator(self._registry).allocate(
            name,
            self._config.env_aliases,
            self._config.envs_per_workspace,
        )

        if not self._write_workspace_self_exclude(name, reporter):
            success = False

        ready_repos = []
        for repo in self._repo_factory.get_project_repos():
            if not self._fs.exists(repo.main_path):
                reporter.repo_error(
                    repo.name,
                    f"source checkout missing at {repo.main_path}. Run `winter ws init` first.",
                )
                success = False
                continue
            ready_repos.append(repo)

        inferred_upstream = self._infer_env_upstream(ready_repos, env_root)

        if not self._run_per_repo(
            ready_repos,
            lambda r: self._reconcile_worktree_repo(r, name, env_root, reporter, inferred_upstream),
        ):
            success = False

        standalones = self._repo_factory.get_standalone_repos()
        if not self._extension_hook_svc.run_env_init_hooks(
            standalones,
            env_root,
            name,
            reporter,
        ):
            success = False

        reporter.target_completed(name, success)
        return success

    def _run_per_repo(self, repos, work_fn) -> bool:
        """Fan work_fn(repo) out across the shared GitOpsService thread pool.

        Each repo's work runs serially within its own task (clone → identity → excludes →
        cmds), but the tasks run concurrently across repos. The pool is capped at
        `GitOpsService.PARALLELISM` so a workspace with many repos doesn't overwhelm
        the SSH connection limit on remote git hosts (Codeberg in particular). Reporter
        calls are thread-safe via internal locking.
        """
        if not repos:
            return True
        success = True
        with self._git_ops.executor() as pool:
            futures = [pool.submit(work_fn, repo) for repo in repos]
            for fut in as_completed(futures):
                if not fut.result():
                    success = False
        return success

    def run_workspace_reconcile_hooks(self, reporter: IInitReporter) -> bool:
        """Fire the `on_workspace_reconcile` hook for every installed extension.

        Call this once per top-level reconcile invocation, after standalones
        have been reconciled (so extension repos exist on disk) and, for the
        all-target path, before the per-env loop.
        """
        standalones = self._repo_factory.get_standalone_repos()
        return self._extension_hook_svc.run_workspace_reconcile_hooks(standalones, reporter)

    def reconcile_all(self, reporter: IInitReporter) -> bool:
        success = self.reconcile_projects(reporter)
        if not self.reconcile_standalones(reporter):
            success = False
        # Fire the workspace-level hook once, after standalones are present on
        # disk and before the per-env loop so extensions see a consistent state.
        if not self.run_workspace_reconcile_hooks(reporter):
            success = False
        for name in self._discover_existing_worktrees():
            if not self.reconcile_env(name, reporter):
                success = False
        return success

    def _discover_existing_worktrees(self) -> list[str]:
        """Use `git worktree list` on the first declared repo to find every existing worktree.

        Git knows exactly where its worktrees live, which is cheaper and more authoritative
        than scanning the filesystem. The source checkout itself is filtered out.
        """
        project_repos = self._repo_factory.get_project_repos()
        if not project_repos:
            return []

        first = project_repos[0]
        if not self._fs.exists(first.main_path):
            return []

        worktree_paths = self._git_repo.list_worktrees(first.main_path)

        names: list[str] = []
        source_main = first.main_path.resolve()
        for raw in worktree_paths:
            worktree_path = raw.resolve()
            if worktree_path == source_main:
                continue
            # worktree path is <workspace>/<name>/<repo_name>; we want <name>
            parent = worktree_path.parent
            if parent.parent.resolve() != self._config.workspace_root.resolve():
                continue
            names.append(parent.name)
        return sorted(set(names))

    # ── Source checkout ───────────────────────────────────────────────────

    def _reconcile_source_checkout(
        self,
        repo: ProjectRepository,
        reporter: IInitReporter,
    ) -> bool:
        repo_path = repo.main_path
        label = repo.name

        try:
            if not self._fs.exists(repo_path):
                if not repo.url:
                    raise RepoError("no `url` declared in config; cannot clone")
                self._git_repo.clone(repo.url, repo_path)
                reporter.repo_action(label, str(repo_path), "cloned")
            else:
                reporter.repo_action(label, str(repo_path), "exists")

            self._apply_identity(repo_path)
            self._write_excludes(repo_path, repo, reporter, str(repo_path))
            self._run_cmds(repo_path, repo, reporter)
        except (RepoError, OSError) as exc:
            reporter.repo_error(label, str(exc))
            return False
        return True

    # ── Standalone repo ───────────────────────────────────────────────────

    def _reconcile_standalone(
        self,
        repo: StandaloneRepository,
        reporter: IInitReporter,
    ) -> bool:
        repo_path = repo.path
        label = repo.name

        try:
            if not self._fs.exists(repo_path):
                if not repo.url:
                    raise RepoError("no `url` declared in config; cannot clone")
                self._fs.mkdir(repo_path.parent, parents=True, exist_ok=True)
                self._git_repo.clone(repo.url, repo_path)
                reporter.repo_action(label, str(repo_path), "cloned")
            else:
                reporter.repo_action(label, str(repo_path), "exists")

            self._apply_identity(repo_path)
            self._write_excludes(repo_path, repo, reporter, str(repo_path))
            self._run_cmds(repo_path, repo, reporter)
            self._apply_standalone_pin(repo, repo_path, reporter)
        except (RepoError, OSError) as exc:
            reporter.repo_error(label, str(exc))
            return False

        ok = self._extension_symlink_svc.process(repo, reporter)
        if self._extension_agent_svc is not None:
            ok &= self._extension_agent_svc.process(repo, reporter)
        return ok

    # ── Standalone pin ────────────────────────────────────────────────────

    def _apply_standalone_pin(
        self,
        repo: StandaloneRepository,
        repo_path: Path,
        reporter: IInitReporter,
    ) -> None:
        """Check out a pinned standalone repo at the correct commit, updating the lock as needed.

        Only runs when ``repo.ref`` is set. Two paths:

        - **Lock present and fresh** (``entry.ref == repo.ref``): check out the
          locked commit without re-resolving or touching the lock. This is the
          reproducible-install path — the locked commit wins even if the remote
          branch or tag has since moved.
        - **Lock absent or stale** (``entry.ref != repo.ref`` or no entry):
          resolve ``repo.ref`` against the on-disk refs, check out the result,
          then rewrite the lock for this repo. Preserves other repos' entries
          (read → replace/add → write full sorted set).

          Before re-resolving on an existing checkout, guard with
          ``is_worktree_clean``; if dirty, raise a clear ``RepoError`` so the
          user can commit/stash first. On a fresh clone the tree is always clean.

        Raises ``RepoError`` on resolution failure or dirty-tree refusal; both
        surface through ``_reconcile_standalone``'s existing ``(RepoError,
        OSError)`` catch.
        """
        if repo.ref is None:
            return
        if self._config_lock_repo is None:
            return

        label = repo.name
        lock_entries = self._config_lock_repo.read()
        existing_entry = lock_entries.get(repo.name)

        if existing_entry is not None and existing_entry.ref == repo.ref:
            # Fresh lock — check out at the locked commit, no network/resolve needed.
            entry = existing_entry
            if entry.kind is RefKind.branch:
                self._git_repo.checkout_branch(repo_path, entry.ref)
            else:
                self._git_repo.checkout_detached(repo_path, entry.commit)
            reporter.repo_action(
                label,
                str(repo_path),
                "pinned",
                f"{entry.kind.value} {entry.commit[:8]}",
            )
        else:
            # Lock absent or stale — need to re-resolve.
            # Guard: refuse if the working tree has uncommitted changes.
            if not self._git_repo.is_worktree_clean(repo_path):
                raise RepoError(
                    f"refusing to re-pin {repo.name!r}: working tree has uncommitted changes; "
                    f"commit or stash first (or run `winter ws fetch {repo.name}` to sync refs)"
                )

            kind, commit = self._git_repo.resolve_ref(repo_path, repo.ref)

            if kind is RefKind.branch:
                self._git_repo.checkout_branch(repo_path, repo.ref)
            else:
                self._git_repo.checkout_detached(repo_path, commit)

            new_entry = LockEntry(name=repo.name, ref=repo.ref, kind=kind, commit=commit)
            # Atomic upsert: preserves other repos' entries even under the
            # parallel standalone fan-out (a plain read-then-write would race
            # and drop concurrently-written entries via last-writer-wins).
            self._config_lock_repo.upsert(new_entry)

            reporter.repo_action(
                label,
                str(repo_path),
                "pinned",
                f"{kind.value} {commit[:8]}",
            )

    # ── Feature worktree ──────────────────────────────────────────────────

    def _reconcile_worktree_repo(
        self,
        repo: ProjectRepository,
        branch_name: str,
        env_root: Path,
        reporter: IInitReporter,
        inferred_upstream: str | None = None,
    ) -> bool:
        worktree_path = env_root / repo.name
        location = str(worktree_path)
        label = repo.name

        try:
            newly_created = not self._fs.exists(worktree_path)
            if newly_created:
                self._create_git_worktree(repo, branch_name, worktree_path)
                reporter.repo_action(label, location, "worktree_created")
            else:
                reporter.repo_action(label, location, "exists")

            self._apply_identity(worktree_path)
            self._write_excludes(worktree_path, repo, reporter, location)
            self._configure_pinned_tracking(repo, worktree_path, reporter)
            self._connect_inferred_upstream(repo, worktree_path, inferred_upstream, reporter, newly_created)
            self._run_cmds(worktree_path, repo, reporter)
        except (RepoError, OSError) as exc:
            reporter.repo_error(label, str(exc))
            return False
        return True

    def _infer_env_upstream(
        self,
        repos: list[ProjectRepository],
        env_root: Path,
    ) -> str | None:
        """Infer a single consistent upstream from the non-pinned worktrees that already have one.

        Returns the common upstream ref string (e.g. `origin/master` for a disconnected env
        or `origin/<feature-branch>` for a connected env) when every non-pinned worktree that
        exists on disk and has a tracking branch agrees on the same ref. Returns None when
        there are no such worktrees or when their upstreams diverge — callers must not guess
        in the ambiguous case.
        """
        upstreams: set[str] = set()
        for repo in repos:
            if repo.pinned:
                continue
            worktree_path = env_root / repo.name
            if not self._fs.exists(worktree_path):
                continue
            upstream = self._git_repo.get_tracking_branch(worktree_path)
            if upstream is not None:
                upstreams.add(upstream)
        if len(upstreams) == 1:
            return next(iter(upstreams))
        return None

    def _connect_inferred_upstream(
        self,
        repo: ProjectRepository,
        worktree_path: Path,
        inferred_upstream: str | None,
        reporter: IInitReporter,
        newly_created: bool = False,
    ) -> None:
        """Wire a non-pinned worktree to `inferred_upstream` when it has no upstream yet.

        Skips pinned repos entirely — their tracking is owned by
        `_configure_pinned_tracking`. Idempotent: a worktree that already existed
        before this init run and already has an upstream is left unchanged —
        that tracking is operator-owned. When `inferred_upstream` is None
        (ambiguous or no siblings), leaves the worktree unconnected for the user
        to wire explicitly with `winter ws connect`.

        `newly_created` is a defense-in-depth backstop for a worktree branch
        created in *this* init run: `_create_git_worktree` creates it with
        `--no-track` precisely so it is never born with an incidental upstream,
        but if it somehow already reports one anyway (e.g. a git version that
        ignores `--no-track`, or a future regression), init — not the operator —
        is still the sole owner of that branch's tracking this run, so the
        inferred upstream wins over whatever it was born with.
        """
        if repo.pinned:
            return
        if inferred_upstream is None:
            return
        current = self._git_repo.get_tracking_branch(worktree_path)
        if current == inferred_upstream:
            return
        if current is not None and not newly_created:
            return
        self._git_repo.set_upstream_to(worktree_path, inferred_upstream)
        self._git_repo.set_push_default_upstream(worktree_path)
        reporter.repo_action(repo.name, str(worktree_path), "upstream_inferred", inferred_upstream)

    def _configure_pinned_tracking(
        self,
        repo: ProjectRepository,
        worktree_path: Path,
        reporter: IInitReporter,
    ) -> None:
        """Wire a pinned worktree to push and pull against `origin/<main-branch>`.

        `winter ws connect` deliberately skips pinned repos — they never participate
        in feature-branch flow — so init is the only place that installs their
        upstream tracking. Pinned repos are owned by the workspace user and
        commits land directly on the main branch, so we also set
        `push.default=upstream` to make `git push` from the worktree branch
        target the main branch. Idempotent: a no-op when both are already in place.
        """
        if not repo.pinned:
            return
        desired = f"origin/{repo.main_branch}"
        changes: list[str] = []
        current = self._git_repo.get_tracking_branch(worktree_path)
        if current != desired:
            self._git_repo.set_upstream_to(worktree_path, desired)
            changes.append(desired)

        if self._git_repo.get_push_default(worktree_path) != "upstream":
            self._git_repo.set_push_default_upstream(worktree_path)
            changes.append("push.default=upstream")

        if changes:
            reporter.repo_action(
                repo.name,
                str(worktree_path),
                "pinned_tracking_set",
                ", ".join(changes),
            )

    def _create_git_worktree(
        self,
        repo: ProjectRepository,
        branch_name: str,
        worktree_path: Path,
    ) -> None:
        existing_heads = set(self._git_repo.get_local_branches(repo.main_path))
        if branch_name in existing_heads:
            self._git_repo.add_worktree(repo.main_path, worktree_path, branch_name)
        else:
            self._git_repo.add_worktree(repo.main_path, worktree_path, branch_name, base_branch=repo.main_branch)

    def _write_workspace_self_exclude(
        self,
        dir_name: str,
        reporter: IInitReporter,
    ) -> bool:
        """Add `/{dir_name}/` to a managed block in the workspace's `.git/info/exclude`.

        The block is namespaced as `winter-dir/{dir_name}` so the orphan-stripping
        pass in ExtensionExcludeService.finalize_excludes leaves it alone (its regex
        rejects names containing `/`).
        """
        return self._write_workspace_exclude_block(
            f"winter-dir/{dir_name}",
            [f"/{dir_name}/"],
            f"/{dir_name}/",
            reporter,
        )

    def _write_workspace_artifact_excludes(self, reporter: IInitReporter) -> bool:
        """Exclude the workspace-root paths winter owns from the workspace repo.

        Covers the `/.winter/logs/` path — the framework's canonical service-log
        location.  winter owns the *convention* here, not any single orchestrator:
        today only winter-service-tmux's file-capture mode writes there, but core
        defining the path is what lets winter point any future provider at it.
        Owning the exclude in core keeps that one decision in one place rather than
        asking each provider to re-declare it.

        Lives at the workspace root — outside any per-env dir block — so it needs
        its own managed exclude entry. The `winter-workspace/` namespace contains a
        `/`, so the extension orphan-stripping pass leaves it alone.
        """
        return self._write_workspace_exclude_block(
            "winter-workspace/artifacts",
            ["/.winter/logs/"],
            "/.winter/logs/",
            reporter,
        )

    def _write_workspace_exclude_block(
        self,
        block_name: str,
        exclude_lines: list[str],
        summary: str,
        reporter: IInitReporter,
    ) -> bool:
        """Write one namespaced managed block to the workspace `.git/info/exclude`.

        Silent no-op when the workspace isn't a git repo (`.git/info/` missing
        and not creatable). Returns False only on a real I/O error.
        """
        begin = GITIGNORE_BEGIN.format(name=block_name)
        end = GITIGNORE_END.format(name=block_name)
        desired_lines = [begin, *exclude_lines, end]

        exclude_path = self._config.workspace_root / ".git" / "info" / "exclude"
        if not self._fs.exists(self._config.workspace_root / ".git"):
            return True

        try:
            existing = self._fs.read_text(exclude_path) if self._fs.exists(exclude_path) else ""
            new_content = replace_or_append_block(existing, begin, end, desired_lines)
            if new_content == existing:
                return True
            self._fs.mkdir(exclude_path.parent, parents=True, exist_ok=True)
            self._fs.write_text(exclude_path, new_content)
        except OSError as exc:
            reporter.repo_error("winter", f".git/info/exclude — {exc}")
            return False

        reporter.repo_action(
            "winter",
            str(exclude_path),
            "workspace_excludes_updated",
            summary,
        )
        return True

    # ── Shared reconcile steps ────────────────────────────────────────────

    def _apply_identity(self, repo_path: Path) -> None:
        identity = self._config.git_identity
        if identity is None:
            return
        self._git_repo.set_user_identity(repo_path, identity.name, identity.email)

    def _write_excludes(
        self,
        repo_path: Path,
        repo: IWorkspaceRepository,
        reporter: IInitReporter,
        location: str,
    ) -> None:
        entries = list(self._config.git_excludes) + list(repo.git_excludes)
        if not entries:
            return

        exclude_path = self._exclude_path(repo_path)
        if exclude_path is None:
            raise RepoError(f"could not locate .git/info/exclude at {repo_path}")

        existing: list[str] = []
        if self._fs.exists(exclude_path):
            existing = self._fs.read_text(exclude_path).splitlines()

        existing_set = {line.strip() for line in existing if line.strip()}
        appended: list[str] = []
        for entry in entries:
            entry = entry.strip()
            if not entry or entry in existing_set:
                continue
            appended.append(entry)
            existing_set.add(entry)

        if not appended:
            return

        self._fs.mkdir(exclude_path.parent, parents=True, exist_ok=True)
        new_lines: list[str] = []
        if existing and not existing[-1].endswith("\n"):
            new_lines.append("")  # ensure separator before our marker
        new_lines.append("# winter-managed")
        new_lines.extend(appended)
        self._fs.append_lines(exclude_path, new_lines)

        reporter.repo_action(repo.name, location, "excludes_updated", ", ".join(appended))

    def _exclude_path(self, repo_path: Path) -> Path | None:
        """Locate .git/info/exclude, following the `.git` file pointer used by worktrees."""
        git_dir = repo_path / ".git"
        if self._fs.is_dir(git_dir):
            return git_dir / "info" / "exclude"
        if self._fs.is_file(git_dir):
            contents = self._fs.read_text(git_dir).strip()
            if contents.startswith("gitdir:"):
                resolved = Path(contents.split(":", 1)[1].strip())
                if not resolved.is_absolute():
                    resolved = (repo_path / resolved).resolve()
                # For worktrees, common info/ lives under the main .git directory.
                common_dir = resolved / "commondir"
                if self._fs.is_file(common_dir):
                    common_rel = self._fs.read_text(common_dir).strip()
                    main_git = (resolved / common_rel).resolve()
                    return main_git / "info" / "exclude"
                return resolved / "info" / "exclude"
        return None

    def _run_cmds(
        self,
        repo_path: Path,
        repo: IWorkspaceRepository,
        reporter: IInitReporter,
    ) -> None:
        if not repo.cmd:
            return
        env = os.environ.copy()
        env.update(TUI_SUPPRESS_ENV)
        for command in repo.cmd:
            reporter.cmd_started(repo.name, command)
            try:
                with self._subprocess.popen(command, cwd=repo_path, env=env, shell=True) as proc:
                    for line in proc.stdout_lines:
                        reporter.cmd_output_line(repo.name, line)
                    returncode = proc.wait()
            except OSError as exc:
                raise RepoError(f"`{command}` — {exc}") from exc
            reporter.cmd_completed(repo.name, command, returncode)
            if returncode != 0:
                raise RepoError(f"`{command}` exited with code {returncode}")
