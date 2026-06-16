from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import (
    ClickRecorder,
    FakeConfigFileReader,
    FakeFilesystem,
    FakeSubprocessRunner,
)
from winter_cli.modules.capability.capability_registry_service import CapabilityRegistryService
from winter_cli.modules.service.handler import ServiceHandler, ServiceParams
from winter_cli.modules.service.models import LogOptions
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver
from winter_cli.modules.service.service_dispatch_service import ServiceDispatchService
from winter_cli.modules.service.service_logs_service import ServiceLogsService
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import StandaloneRepository

WS = Path("/ws")
ENTRYPOINT = str(WS / "winter-service-tmux/workflow/service")


class _StubRepoFactory:
    def __init__(self, repos: list[StandaloneRepository]) -> None:
        self._repos = repos

    def get_standalone_repos(self) -> list[StandaloneRepository]:
        return self._repos


def _resolver(runner: FakeSubprocessRunner) -> ServiceOrchestratorResolver:
    repo = StandaloneRepository(name="winter-service-tmux", path=WS / "winter-service-tmux")
    loader = ExtensionManifestLoader(
        config_file_reader=FakeConfigFileReader(
            {repo.path / EXT_MANIFEST: {"orchestrate_services": "workflow/service"}}
        )
    )
    fs = FakeFilesystem(files={repo.path / EXT_MANIFEST: "", repo.path / "workflow/service": ""})
    registry = CapabilityRegistryService(
        repo_factory=_StubRepoFactory([repo]),
        manifest_loader=loader,
        bindings={"service": "winter-service-tmux"},
        fs=fs,
    )
    return ServiceOrchestratorResolver(
        registry=registry,
        repo_factory=_StubRepoFactory([repo]),
        manifest_loader=loader,
        fs=fs,
    )


def _handler(runner: FakeSubprocessRunner, click: Any = None) -> ServiceHandler:
    res = _resolver(runner)
    dispatch = ServiceDispatchService(subprocess_runner=runner, orchestrator_resolver=res, workspace_root=WS)
    click_obj = click or ClickRecorder()
    logs = ServiceLogsService(subprocess_runner=runner, orchestrator_resolver=res, click=click_obj, workspace_root=WS)
    return ServiceHandler(dispatch, logs)


# ── dispatch actions ──────────────────────────────────────────────────────────


def test_handler_up_invokes_entrypoint_with_action_and_env() -> None:
    runner = FakeSubprocessRunner()
    _handler(runner).run(ServiceParams(action="up", env="alpha"))
    assert runner.call_calls == [([ENTRYPOINT, "up", "alpha"], WS)]


def test_handler_down_invokes_correct_argv() -> None:
    runner = FakeSubprocessRunner()
    _handler(runner).run(ServiceParams(action="down", env="beta"))
    assert runner.call_calls == [([ENTRYPOINT, "down", "beta"], WS)]


def test_handler_status_exits_zero_without_raising() -> None:
    runner = FakeSubprocessRunner()
    _handler(runner).run(ServiceParams(action="status", env="alpha"))


def test_handler_restart_sets_service_name_env_var() -> None:
    runner = FakeSubprocessRunner()
    _handler(runner).run(ServiceParams(action="restart", env="alpha", service_name="api"))
    assert runner.call_calls == [([ENTRYPOINT, "restart", "alpha"], WS)]
    assert len(runner.call_envs) == 1
    env = runner.call_envs[0]
    assert env["WINTER_SERVICE_NAME"] == "api"
    assert "PATH" in env
    assert env["WINTER_WORKSPACE_DIR"] == str(WS)
    assert env["WINTER_EXT_DIR"] == str(WS / "winter-service-tmux")
    assert env["WINTER_EXT_PREFIX"] == "winter-service-tmux"


def test_handler_adopts_nonzero_exit_code() -> None:
    runner = FakeSubprocessRunner(call_responses={f"{ENTRYPOINT} status alpha": 7})
    with pytest.raises(SystemExit) as excinfo:
        _handler(runner).run(ServiceParams(action="status", env="alpha"))
    assert excinfo.value.code == 7


# ── logs via run_logs ─────────────────────────────────────────────────────────


def _default_log_options(**kwargs: Any) -> LogOptions:
    defaults: dict[str, Any] = {
        "services": (),
        "follow": False,
        "tail": 200,
        "since_rfc3339": "",
        "until_rfc3339": "",
        "timestamps": False,
    }
    defaults.update(kwargs)
    return LogOptions(**defaults)


def test_handler_run_logs_streams_rendered_output() -> None:
    ndjson_lines = [
        '{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"started"}',
        '{"ts":"2026-06-13T10:00:02Z","svc":"api","msg":"ready"}',
    ]
    runner = FakeSubprocessRunner(popen_responses={f"{ENTRYPOINT} logs alpha": (ndjson_lines, 0)})
    recorder = ClickRecorder()
    _handler(runner, recorder).run_logs("alpha", _default_log_options())
    # Both lines rendered, plain msg only (single service in stream but no explicit filter).
    assert any("started" in m for m, _ in recorder.calls)
    assert any("ready" in m for m, _ in recorder.calls)


def test_handler_run_logs_exits_nonzero_on_orchestrator_error() -> None:
    runner = FakeSubprocessRunner(popen_responses={f"{ENTRYPOINT} logs alpha": ([], 2)})
    with pytest.raises(SystemExit) as excinfo:
        _handler(runner, ClickRecorder()).run_logs("alpha", _default_log_options())
    assert excinfo.value.code == 2


def test_handler_run_logs_sets_workspace_context_env_vars() -> None:
    """Logs stream injects WINTER_WORKSPACE_DIR, WINTER_EXT_DIR, WINTER_EXT_PREFIX, and cwd."""
    runner = FakeSubprocessRunner(popen_responses={f"{ENTRYPOINT} logs alpha": ([], 0)})
    _handler(runner, ClickRecorder()).run_logs("alpha", _default_log_options())
    assert len(runner.popen_calls) == 1
    assert runner.popen_calls[0][1] == WS
    assert len(runner.popen_envs) == 1
    env = runner.popen_envs[0]
    assert env["WINTER_WORKSPACE_DIR"] == str(WS)
    assert env["WINTER_EXT_DIR"] == str(WS / "winter-service-tmux")
    assert env["WINTER_EXT_PREFIX"] == "winter-service-tmux"
