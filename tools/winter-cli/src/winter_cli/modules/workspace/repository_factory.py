from __future__ import annotations

from winter_cli.config.models import (
    ProjectRepositoryConfig,
    SingletonType,
    StandaloneRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.modules.workspace.models import (
    ProjectRepository,
    StandaloneRepository,
)

_SINGLETON_PATHS: dict[SingletonType, tuple[str, ...]] = {
    SingletonType.workspace: (),
    SingletonType.product: ("product",),
    SingletonType.harness: ("ai", "harness"),
}


class RepositoryFactory:
    def __init__(self, config: WorkspaceConfig) -> None:
        self._config = config

    def get_project_repos(self) -> list[ProjectRepository]:
        result: list[ProjectRepository] = []
        for r in self._config.project_repos:
            name = self._resolve_project_name(r)
            result.append(
                ProjectRepository(
                    name=name,
                    main_path=self._config.workspace_root / "projects" / name,
                    main_branch=r.main_branch or self._config.main_branch,
                    pinned=r.pinned,
                    url=r.url,
                    git_excludes=list(r.git_excludes),
                    cmd=list(r.cmd),
                )
            )
        return result

    def get_singleton_repos(self) -> list[StandaloneRepository]:
        """Return implicit singletons — workspace, product, harness — discovered from the filesystem."""
        result: list[StandaloneRepository] = []
        for r in self._config.singleton_repos:
            parts = _SINGLETON_PATHS[r.type]
            path = self._config.workspace_root / "/".join(parts) if parts else self._config.workspace_root
            result.append(StandaloneRepository(name=r.name, path=path))
        return result

    def get_standalone_repos(self) -> list[StandaloneRepository]:
        """Return user-declared standalone repos from [[standalone_repository]] in config.

        These are cloned at the workspace root (or under the configured `path`) by
        `winter ws init` and may opt into extension behavior via a winter-ext.toml
        file at the repo root.
        """
        result: list[StandaloneRepository] = []
        for r in self._config.standalone_repos:
            name = self._resolve_standalone_name(r)
            relative_path = r.path or name
            result.append(
                StandaloneRepository(
                    name=name,
                    path=self._config.workspace_root / relative_path,
                    main_branch=r.main_branch or self._config.main_branch,
                    url=r.url,
                    git_excludes=list(r.git_excludes),
                    cmd=list(r.cmd),
                    prefix=r.prefix,
                )
            )
        return result

    def _resolve_project_name(self, repo: ProjectRepositoryConfig) -> str:
        if repo.name:
            return repo.name
        if repo.url:
            return self.name_from_url(repo.url)
        raise ValueError("project repo must declare either `name` or `url`")

    def _resolve_standalone_name(self, repo: StandaloneRepositoryConfig) -> str:
        if repo.name:
            return repo.name
        if repo.url:
            return self.name_from_url(repo.url)
        raise ValueError("standalone repo must declare either `name` or `url`")

    @staticmethod
    def name_from_url(url: str) -> str:
        """Derive a repo name from a clone URL.

        Takes everything after the last `/` or `:` and strips a trailing `.git`. Handles
        the SSH, HTTPS, and Azure DevOps URL shapes:
            git@codeberg.org:pgross/winter.git → winter
            git@ssh.dev.azure.com:v3/paul0819/Salacia/Salacia → Salacia
            https://github.com/foo/bar.git → bar
        """
        stripped = url.rstrip("/")
        cut = max(stripped.rfind("/"), stripped.rfind(":"))
        candidate = stripped[cut + 1 :] if cut != -1 else stripped
        return candidate.removesuffix(".git")
