from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

import click

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from winter_cli.modules.workspace.models import StandaloneRepository, Workspace
from winter_cli.plugins.types import (
    ActionScope,
    EnvironmentDecorator,
    PluginRegistration,
    TuiAction,
    WinterPlugin,
    WorktreeRepoDecorator,
)

USER_PLUGINS_DIR = Path.home() / ".config" / "winter" / "plugins"

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self) -> None:
        self.plugins: list[WinterPlugin] = []
        self.commands: list[click.BaseCommand] = []
        self.worktree_repo_decorators: list[WorktreeRepoDecorator] = []
        self.environment_decorators: list[EnvironmentDecorator] = []
        self.screens: list = []
        self.tui_actions: list[TuiAction] = []

    def actions_for_scope(self, scope: ActionScope) -> list[TuiAction]:
        return [a for a in self.tui_actions if a.scope == scope]

    @classmethod
    def load(
        cls,
        workspace: Workspace,
        standalone_repos: list[StandaloneRepository] | None = None,
    ) -> PluginRegistry:
        """Discover and load every plugin that contributes to this workspace.

        Three sources, in priority order (first wins on name collision):
          1. Workspace-local: `<workspace>/.winter/plugins/<name>/plugin.py`
          2. User-global:     `~/.config/winter/plugins/<name>/plugin.py`
          3. Installed extensions: `<standalone_repo>/plugin.py` — lets a
             winter extension ship a dashboard plugin alongside its hooks
             without the user having to copy anything into .winter/plugins/.
        """
        registry = cls()
        workspace_plugins_dir = workspace.root_path / ".winter" / "plugins"
        seen: set[str] = set()

        for plugins_dir in [workspace_plugins_dir, USER_PLUGINS_DIR]:
            if not plugins_dir.is_dir():
                continue
            for plugin_dir in sorted(plugins_dir.iterdir()):
                if not plugin_dir.is_dir() or plugin_dir.name in seen:
                    continue
                if not (plugin_dir / "plugin.py").is_file():
                    continue
                registry._load_plugin(plugin_dir)
                seen.add(plugin_dir.name)

        for repo in standalone_repos or []:
            if repo.name in seen:
                continue
            if not repo.path.is_dir() or not (repo.path / "plugin.py").is_file():
                continue
            registry._load_plugin(repo.path)
            seen.add(repo.name)

        return registry

    def _load_plugin(self, plugin_dir: Path) -> None:
        plugin_name = plugin_dir.name
        entry_point = plugin_dir / "plugin.py"
        config = self._load_config(plugin_dir)

        try:
            spec = importlib.util.spec_from_file_location(
                f"winter_plugin_{plugin_name}",
                entry_point,
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception:
            logger.warning("Failed to load plugin '%s'", plugin_name, exc_info=True)
            return

        if not hasattr(module, "create_plugin"):
            logger.warning("Plugin '%s' has no create_plugin() function, skipping", plugin_name)
            return

        plugin: WinterPlugin = module.create_plugin()
        registration: PluginRegistration = plugin.register(config)
        self._apply(plugin, registration)

    def _apply(self, plugin: WinterPlugin, registration: PluginRegistration) -> None:
        self.plugins.append(plugin)
        self.commands.extend(registration.commands)
        self.worktree_repo_decorators.extend(registration.worktree_repo_decorators)
        self.environment_decorators.extend(registration.environment_decorators)
        self.screens.extend(registration.tui_screens)
        self.tui_actions.extend(registration.tui_actions)

    @staticmethod
    def _load_config(plugin_dir: Path) -> dict:
        config_path = plugin_dir / "config.toml"
        if not config_path.is_file():
            return {}
        with config_path.open("rb") as f:
            return tomllib.load(f)
