from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.conftest import FakeConfigFileReader, FakeFilesystem, FakeSubprocessRunner
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver
from winter_cli.modules.service.service_dispatch_service import ServiceDispatchService
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


def _configured_resolver() -> ServiceOrchestratorResolver:
    """A fully-wired resolver whose orchestrator declares `orchestrate_services = 'workflow/service'`."""
    repo = _tmux_repo()
    entrypoint = repo.path / "workflow/service"
    return _resolver(
        orchestrator="winter-service-tmux",
        repos=[repo],
        manifests={repo.path / EXT_MANIFEST: {"orchestrate_services": "workflow/service"}},
        files={repo.path / EXT_MANIFEST: "", entrypoint: ""},
    )


def _service(runner: FakeSubprocessRunner | None = None) -> ServiceDispatchService:
    return ServiceDispatchService(
        subprocess_runner=runner or FakeSubprocessRunner(),
        orchestrator_resolver=_configured_resolver(),
    )


# ── happy path: dispatch, env var forwarding, exit-code passthrough ───────────


def test_dispatch_executes_entrypoint_with_action_and_env() -> None:
    runner = FakeSubprocessRunner()
    code = _service(runner).dispatch("up", "alpha")
    assert code == 0
    assert runner.call_calls == [([str(WS / "winter-service-tmux/workflow/service"), "up", "alpha"], None)]


def test_dispatch_passes_extra_env_to_call() -> None:
    runner = FakeSubprocessRunner()
    _service(runner).dispatch("restart", "alpha", {"WINTER_SERVICE_NAME": "backend"})
    assert len(runner.call_envs) == 1
    env = runner.call_envs[0]
    assert env["WINTER_SERVICE_NAME"] == "backend"
    assert "PATH" in env


def test_dispatch_restart_preserves_inherited_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: restart must not wipe the parent environment."""
    monkeypatch.setenv("WINTER_TEST_SENTINEL", "canary-value")
    runner = FakeSubprocessRunner()
    _service(runner).dispatch("restart", "alpha", {"WINTER_SERVICE_NAME": "worker"})
    assert len(runner.call_envs) == 1
    env = runner.call_envs[0]
    assert env["WINTER_SERVICE_NAME"] == "worker"
    assert env["WINTER_TEST_SENTINEL"] == "canary-value"
    assert env.items() >= os.environ.items()


def test_dispatch_passes_exit_code_through_unmodified() -> None:
    entrypoint = str(WS / "winter-service-tmux/workflow/service")
    runner = FakeSubprocessRunner(call_responses={f"{entrypoint} status alpha": 3})
    assert _service(runner).dispatch("status", "alpha") == 3


# ── misconfiguration errors (tested via the resolver) ────────────────────────


def test_no_orchestrator_registered_raises() -> None:
    res = _resolver(orchestrator=None, repos=[], manifests={}, files={})
    svc = ServiceDispatchService(subprocess_runner=FakeSubprocessRunner(), orchestrator_resolver=res)
    with pytest.raises(RepoError, match="no service orchestrator registered"):
        svc.dispatch("up", "alpha")


def test_unknown_extension_name_raises() -> None:
    res = _resolver(orchestrator="winter-service-docker", repos=[_tmux_repo()], manifests={}, files={})
    svc = ServiceDispatchService(subprocess_runner=FakeSubprocessRunner(), orchestrator_resolver=res)
    with pytest.raises(RepoError, match="not an installed extension"):
        svc.dispatch("up", "alpha")


def test_extension_missing_service_key_raises() -> None:
    repo = _tmux_repo()
    res = _resolver(
        orchestrator="winter-service-tmux",
        repos=[repo],
        manifests={repo.path / EXT_MANIFEST: {}},
        files={repo.path / EXT_MANIFEST: ""},
    )
    svc = ServiceDispatchService(subprocess_runner=FakeSubprocessRunner(), orchestrator_resolver=res)
    with pytest.raises(RepoError, match="declares no `orchestrate_services` entrypoint"):
        svc.dispatch("up", "alpha")


def test_missing_entrypoint_file_raises() -> None:
    repo = _tmux_repo()
    res = _resolver(
        orchestrator="winter-service-tmux",
        repos=[repo],
        manifests={repo.path / EXT_MANIFEST: {"orchestrate_services": "workflow/service"}},
        files={repo.path / EXT_MANIFEST: ""},  # manifest present, entrypoint absent
    )
    svc = ServiceDispatchService(subprocess_runner=FakeSubprocessRunner(), orchestrator_resolver=res)
    with pytest.raises(RepoError, match="entrypoint not found"):
        svc.dispatch("up", "alpha")
