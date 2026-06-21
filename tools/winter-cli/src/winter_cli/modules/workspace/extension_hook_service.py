from __future__ import annotations

import logging
from pathlib import Path

from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.core.extension_invocation import build_extension_env
from winter_cli.core.filesystem import IFilesystemWriter
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.workspace.env_index import resolve_env_index
from winter_cli.modules.workspace.env_index_registry import IEnvIndexRegistry
from winter_cli.modules.workspace.extension_manifest import (
    EXT_MANIFEST,
    HOOK_ON_ENV_DESTROY,
    HOOK_ON_ENV_INIT,
    HOOK_ON_WORKSPACE_RECONCILE,
    ExtensionManifest,
    ExtensionManifestLoader,
)
from winter_cli.modules.workspace.init_reporter import IInitReporter
from winter_cli.modules.workspace.models import RepoError, StandaloneRepository

logger = logging.getLogger(__name__)


class ExtensionHookService:
    """Runs each installed extension's `on_env_init` / `on_env_destroy` /
    `on_workspace_reconcile` scripts.

    The env-hook contract: each script runs from the env's directory with
    `WINTER_WORKSPACE_DIR`, `WINTER_EXT_DIR`, `WINTER_EXT_PREFIX`,
    `WINTER_ENV`, `WINTER_ENV_INDEX`, and `WINTER_PORT_BASE` in the
    environment.

    The workspace-hook contract: each script runs from the workspace root with
    only `WINTER_WORKSPACE_DIR`, `WINTER_EXT_DIR`, and `WINTER_EXT_PREFIX` in
    the environment — no `WINTER_ENV`, `WINTER_ENV_INDEX`, or `WINTER_PORT_BASE`.
    `on_workspace_reconcile` fires once per workspace reconcile (`winter ws init`
    no-target/all-target) after standalones are reconciled (so extension repos
    exist on disk), and before per-env loops.

    Hooks let extensions contribute setup/teardown steps that don't fit the
    symlink-skills/agents model.

    Error-handling shape: per-extension hook execution is its own wrap site
    (`_run_one_hook`). The aggregator collects per-extension booleans so
    one extension's broken manifest or non-zero hook doesn't suppress the
    others.
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        fs: IFilesystemWriter,
        subprocess_runner: ISubprocessRunner,
        manifest_loader: ExtensionManifestLoader,
        registry: IEnvIndexRegistry | None = None,
    ) -> None:
        self._config = config
        self._fs = fs
        self._subprocess = subprocess_runner
        self._manifest_loader = manifest_loader
        self._registry = registry

    def run_env_init_hooks(
        self,
        repos: list[StandaloneRepository],
        env_root: Path,
        env_name: str,
        reporter: IInitReporter,
    ) -> bool:
        """Run each installed extension's `on_env_init` hook.

        Called from `winter ws init <name>` after every project repo's
        worktree has been created and its `cmd` list has run. The hook
        executes from the new env's directory so it can drop files in
        place, with env vars identifying the workspace, the extension,
        and the feature env.
        """
        return self._run_env_hooks(
            repos,
            env_root,
            env_name,
            HOOK_ON_ENV_INIT,
            reporter,
        )

    def run_env_destroy_hooks(
        self,
        repos: list[StandaloneRepository],
        env_root: Path,
        env_name: str,
        reporter: IInitReporter,
    ) -> bool:
        """Run each installed extension's `on_env_destroy` hook.

        Called from `winter ws destroy <name>` *before* any file removal,
        so extensions can clean up per-env resources (tmux sessions,
        watchers, tunnels, provisioned DBs) while the env still exists on
        disk. The env-var contract matches `on_env_init`.

        Returns False if any hook errored or exited non-zero. Callers
        decide whether to abort teardown on that signal (`--strict`) or
        log and continue.
        """
        return self._run_env_hooks(
            repos,
            env_root,
            env_name,
            HOOK_ON_ENV_DESTROY,
            reporter,
        )

    def run_workspace_reconcile_hooks(
        self,
        repos: list[StandaloneRepository],
        reporter: IInitReporter,
    ) -> bool:
        """Run each installed extension's `on_workspace_reconcile` hook.

        Called once per workspace reconcile (`winter ws init` no-target or
        all-target) after standalones are reconciled so extension repos exist
        on disk. Runs from the workspace root with only `WINTER_WORKSPACE_DIR`,
        `WINTER_EXT_DIR`, and `WINTER_EXT_PREFIX` — no env-scoped vars.

        Returns False if any hook errored or exited non-zero.
        """
        hook_name = HOOK_ON_WORKSPACE_RECONCILE
        logger.info("run %s hooks: repos=%d", hook_name, len(repos))
        if self._config.adopt_extensions == AdoptExtensions.none:
            logger.info("%s: adopt_extensions=none, skipping", hook_name)
            return True

        workspace_root = self._config.workspace_root
        success = True
        for repo in repos:
            if not self._fs.exists(repo.path):
                continue
            manifest_path = repo.path / EXT_MANIFEST
            if not self._fs.is_file(manifest_path):
                continue
            if not self._run_one_hook(repo, manifest_path, hook_name, workspace_root, None, reporter):
                logger.warning("%s failed for extension %s", hook_name, repo.name)
                success = False
        return success

    def _run_env_hooks(
        self,
        repos: list[StandaloneRepository],
        env_root: Path,
        env_name: str,
        hook_name: str,
        reporter: IInitReporter,
    ) -> bool:
        """Aggregate per-extension hook results. Each extension is its own wrap site."""
        logger.info("run %s hooks: env=%s repos=%d", hook_name, env_name, len(repos))
        if self._config.adopt_extensions == AdoptExtensions.none:
            logger.info("%s: adopt_extensions=none, skipping", hook_name)
            return True

        success = True
        for repo in repos:
            if not self._fs.exists(repo.path):
                continue
            manifest_path = repo.path / EXT_MANIFEST
            if not self._fs.is_file(manifest_path):
                continue
            if not self._run_one_hook(repo, manifest_path, hook_name, env_root, env_name, reporter):
                logger.warning("%s failed for extension %s", hook_name, repo.name)
                success = False
        return success

    def _run_one_hook(
        self,
        repo: StandaloneRepository,
        manifest_path: Path,
        hook_name: str,
        cwd: Path,
        env_name: str | None,
        reporter: IInitReporter,
    ) -> bool:
        """Load the manifest, find the hook, and execute it.

        `env_name` is None for workspace-level hooks (no WINTER_ENV* vars);
        a string for env-scoped hooks (WINTER_ENV, WINTER_ENV_INDEX,
        WINTER_PORT_BASE are added).
        """
        try:
            manifest = self._manifest_loader.load(repo, manifest_path)
            hook = manifest.hooks.get(hook_name)
            if not hook:
                return True
            self._run_hook(repo, manifest, hook, hook_name, cwd, env_name, reporter)
        except (RepoError, OSError) as exc:
            reporter.repo_error(repo.name, str(exc))
            return False
        return True

    def _run_hook(
        self,
        repo: StandaloneRepository,
        manifest: ExtensionManifest,
        hook: str,
        hook_name: str,
        cwd: Path,
        env_name: str | None,
        reporter: IInitReporter,
    ) -> None:
        script_path = (repo.path / hook).resolve()
        try:
            script_path.relative_to(repo.path.resolve())
        except ValueError as exc:
            raise RepoError(
                f"hook path `{hook}` escapes the extension directory; refusing to run",
            ) from exc
        if not self._fs.is_file(script_path):
            raise RepoError(f"hook `{hook}` not found at {script_path}")
        if not self._fs.access_x_ok(script_path):
            raise RepoError(f"hook `{hook}` is not executable")

        config_dir = (
            repo.config_dir
            if repo.config_dir is not None
            else (self._config.workspace_root / ".winter" / "config" / repo.name)
        )
        env = build_extension_env(
            workspace_root=self._config.workspace_root,
            ext_dir=repo.path,
            prefix=manifest.prefix,
            config_dir=config_dir,
        )
        if env_name is not None:
            # Resolve registry-first so WINTER_ENV_INDEX/WINTER_PORT_BASE agree
            # with the .winter.env that init_service already wrote.  Fall back
            # to the config-aware formula for envs not yet recorded (pre-init
            # hooks or pre-registry environments).
            index = self._registry.get_index(env_name) if self._registry is not None else None
            if index is None:
                index = resolve_env_index(
                    env_name,
                    self._config.env_aliases,
                    self._config.envs_per_workspace,
                )
            env.update(
                {
                    "WINTER_ENV": env_name,
                    "WINTER_ENV_INDEX": str(index),
                    "WINTER_PORT_BASE": str(self._config.port_base_for_index(index)),
                }
            )

        label = f"hook {hook_name}"
        reporter.cmd_started(repo.name, label)
        try:
            with self._subprocess.popen([str(script_path)], cwd=cwd, env=env) as proc:
                for line in proc.stdout_lines:
                    reporter.cmd_output_line(repo.name, line)
                returncode = proc.wait()
        except OSError as exc:
            raise RepoError(f"hook {hook_name} — {exc}") from exc
        reporter.cmd_completed(repo.name, label, returncode)
        if returncode != 0:
            raise RepoError(f"hook {hook_name} exited with code {returncode}")
        reporter.repo_action(repo.name, str(cwd), "hook_ran", hook_name)
