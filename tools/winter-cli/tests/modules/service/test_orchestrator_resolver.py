from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeConfigFileReader, FakeFilesystem
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import RepoError, StandaloneRepository

WS = Path("/ws")


class _StubRepoFactory:
    def __init__(self, repos: list[StandaloneRepository]) -> None:
        self._repos = repos

    def get_standalone_repos(self) -> list[StandaloneRepository]:
        return self._repos


def _resolver(
    *,
    orchestrator: str | None,
    repos: list[StandaloneRepository],
    manifests: dict[Path, dict],
    files: dict[Path, str],
) -> ServiceOrchestratorResolver:
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(manifests))
    return ServiceOrchestratorResolver(
        service_orchestrator=orchestrator,
        repo_factory=_StubRepoFactory(repos),
        manifest_loader=loader,
        fs=FakeFilesystem(files=files),
    )


def _tmux_repo() -> StandaloneRepository:
    return StandaloneRepository(name="winter-service-tmux", path=WS / "winter-service-tmux")


def _configured() -> ServiceOrchestratorResolver:
    repo = _tmux_repo()
    entrypoint = repo.path / "workflow/service"
    return _resolver(
        orchestrator="winter-service-tmux",
        repos=[repo],
        manifests={repo.path / EXT_MANIFEST: {"orchestrate_services": "workflow/service"}},
        files={repo.path / EXT_MANIFEST: "", entrypoint: ""},
    )


def test_resolve_returns_correct_entrypoint_path() -> None:
    path = _configured().resolve()
    assert path == WS / "winter-service-tmux/workflow/service"


def test_no_orchestrator_registered_raises() -> None:
    res = _resolver(orchestrator=None, repos=[], manifests={}, files={})
    with pytest.raises(RepoError, match="no service orchestrator registered"):
        res.resolve()


def test_unknown_extension_name_raises() -> None:
    res = _resolver(orchestrator="winter-service-docker", repos=[_tmux_repo()], manifests={}, files={})
    with pytest.raises(RepoError, match="not an installed extension"):
        res.resolve()


def test_extension_missing_orchestrate_services_key_raises() -> None:
    repo = _tmux_repo()
    res = _resolver(
        orchestrator="winter-service-tmux",
        repos=[repo],
        manifests={repo.path / EXT_MANIFEST: {}},
        files={repo.path / EXT_MANIFEST: ""},
    )
    with pytest.raises(RepoError, match="declares no `orchestrate_services` entrypoint"):
        res.resolve()


def test_missing_entrypoint_file_raises() -> None:
    repo = _tmux_repo()
    res = _resolver(
        orchestrator="winter-service-tmux",
        repos=[repo],
        manifests={repo.path / EXT_MANIFEST: {"orchestrate_services": "workflow/service"}},
        files={repo.path / EXT_MANIFEST: ""},  # manifest present, entrypoint absent
    )
    with pytest.raises(RepoError, match="entrypoint not found"):
        res.resolve()
