from __future__ import annotations

from pathlib import Path

from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import RepoError, StandaloneRepository
from winter_cli.modules.workspace.repository_factory import IStandaloneRepoProvider


class ServiceOrchestratorResolver:
    """Resolves the registered service orchestrator entrypoint.

    The four resolution failures each raise a distinct `RepoError`:
      1. no `service_orchestrator` registered in `.winter/config.toml`,
      2. the configured name matches no installed extension,
      3. the matched extension declares no `orchestrate_services` entrypoint,
      4. the declared entrypoint file is missing on disk.

    Shared by `ServiceDispatchService` and `ServiceLogsService` so orchestrator
    resolution logic is not duplicated.
    """

    def __init__(
        self,
        service_orchestrator: str | None,
        repo_factory: IStandaloneRepoProvider,
        manifest_loader: ExtensionManifestLoader,
        fs: IFilesystemReader,
    ) -> None:
        self._service_orchestrator = service_orchestrator
        self._repo_factory = repo_factory
        self._manifest_loader = manifest_loader
        self._fs = fs

    def resolve(self) -> Path:
        """Return the resolved entrypoint path or raise RepoError."""
        name = self._service_orchestrator
        if not name:
            raise RepoError(
                "no service orchestrator registered — set "
                '`service_orchestrator = "<extension-name>"` in .winter/config.toml '
                "(it must name an installed extension that declares an `orchestrate_services` "
                "entrypoint in its winter-ext.toml)."
            )

        repo = self._find_extension(name)
        if repo is None:
            raise RepoError(
                f"service orchestrator {name!r} is not an installed extension — "
                "`service_orchestrator` must match the name of a "
                "[[standalone_repository]] in .winter/config.toml."
            )

        manifest = self._manifest_loader.load(repo, repo.path / EXT_MANIFEST)
        if not manifest.orchestrate_services:
            raise RepoError(
                f"service orchestrator {name!r} declares no `orchestrate_services` entrypoint — "
                f'add `orchestrate_services = "<path>"` to {repo.path / EXT_MANIFEST}.'
            )

        entrypoint = repo.path / manifest.orchestrate_services
        if not self._fs.is_file(entrypoint):
            manifest_path = repo.path / EXT_MANIFEST
            raise RepoError(
                f"service orchestrator {name!r} entrypoint not found at {entrypoint} "
                f'(declared as `orchestrate_services = "{manifest.orchestrate_services}"` in {manifest_path}).'
            )
        return entrypoint

    def _find_extension(self, name: str) -> StandaloneRepository | None:
        for repo in self._repo_factory.get_standalone_repos():
            if repo.name == name:
                return repo
        return None
