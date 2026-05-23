from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from winter_cli.config.models import (
    AdoptExtensions,
    GitIdentity,
    ProjectRepositoryConfig,
    SingletonRepository,
    SingletonType,
    StandaloneRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.util import deep_merge

WINTER_DIR = ".winter"
CONFIG_FILE = "config.toml"
LOCAL_CONFIG_FILE = "config.local.toml"


class WorkspaceConfigService:
    def load(self) -> WorkspaceConfig:
        workspace_root = self._find_workspace_root()
        raw = self._read_config(workspace_root / WINTER_DIR / CONFIG_FILE)
        overlay = self._read_config(workspace_root / WINTER_DIR / LOCAL_CONFIG_FILE)
        merged = deep_merge(raw, overlay)

        singletons: list[SingletonRepository] = [
            SingletonRepository(name=workspace_root.name, type=SingletonType.workspace),
        ]
        if (workspace_root / "product").is_dir():
            singletons.append(SingletonRepository(name="product", type=SingletonType.product))
        if (workspace_root / "ai" / "harness" / ".git").exists():
            singletons.append(SingletonRepository(name="harness", type=SingletonType.harness))

        project_repos: list[ProjectRepositoryConfig] = []
        for entry in merged.get("project_repository", []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            url = entry.get("url")
            if not name and not url:
                continue
            project_repos.append(
                ProjectRepositoryConfig(
                    name=name,
                    url=url,
                    main_branch=entry.get("main_branch"),
                    pinned=bool(entry.get("pinned", False)),
                    git_excludes=list(entry.get("git_excludes", []) or []),
                    cmd=list(entry.get("cmd", []) or []),
                )
            )

        standalone_repos: list[StandaloneRepositoryConfig] = []
        for entry in merged.get("standalone_repository", []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            url = entry.get("url")
            if not name and not url:
                continue
            path_value = entry.get("path")
            if path_value is not None:
                self._validate_relative_path(path_value, name or url)
            standalone_repos.append(
                StandaloneRepositoryConfig(
                    name=name,
                    url=url,
                    main_branch=entry.get("main_branch"),
                    path=path_value,
                    prefix=entry.get("prefix"),
                    git_excludes=list(entry.get("git_excludes", []) or []),
                    cmd=list(entry.get("cmd", []) or []),
                )
            )

        user = ((merged.get("git") or {}).get("user")) or {}
        git_identity = (
            GitIdentity(name=user["name"], email=user["email"]) if user.get("name") and user.get("email") else None
        )

        main_branch = merged.get("main_branch") or "main"

        adopt_value = merged.get("adopt_extensions", "winter")
        try:
            adopt_extensions = AdoptExtensions(adopt_value)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid adopt_extensions value: {adopt_value!r}. Must be one of: 'none', 'winter', 'all'."
            ) from exc

        return WorkspaceConfig(
            workspace_root=workspace_root,
            session_prefix=merged.get("session_prefix", "winter"),
            main_branch=main_branch,
            git_excludes=list(merged.get("git_excludes", []) or []),
            git_identity=git_identity,
            adopt_extensions=adopt_extensions,
            singleton_repos=singletons,
            project_repos=project_repos,
            standalone_repos=standalone_repos,
        )

    def _find_workspace_root(self) -> Path:
        current = Path.cwd()
        for directory in [current, *current.parents]:
            if (directory / WINTER_DIR).is_dir():
                return directory
        raise RuntimeError(
            f"Could not find workspace root from {current}. Expected to find a {WINTER_DIR}/ directory in a parent."
        )

    def _read_config(self, path: Path) -> dict:
        if not path.is_file():
            return {}
        with path.open("rb") as f:
            return tomllib.load(f)

    @staticmethod
    def _validate_relative_path(value: str, label: str | None) -> None:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeError(
                f"Invalid path {value!r} for standalone repo {label!r}: "
                f"must be a relative path under the workspace root with no `..` segments."
            )
