from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import (
    FakeConfigFileReader,
    FakeFilesystem,
    FakeInitReporter,
    FakeSubprocessRunner,
)
from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.modules.workspace.extension_hook_service import ExtensionHookService
from winter_cli.modules.workspace.extension_manifest import ExtensionManifestLoader
from winter_cli.modules.workspace.models import StandaloneRepository

WORKSPACE_ROOT = Path("/ws")


@pytest.fixture
def workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=WORKSPACE_ROOT,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
    )


def _service(
    workspace_config: WorkspaceConfig,
    fs: FakeFilesystem,
    config_files: dict[Path, dict],
    subprocess: FakeSubprocessRunner,
) -> ExtensionHookService:
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    return ExtensionHookService(
        config=workspace_config,
        fs=fs,
        subprocess_runner=subprocess,
        manifest_loader=loader,
    )


def test_run_env_init_hook_streams_output_and_succeeds(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """Happy-path: a hook script runs, lines stream to the reporter, exit 0."""
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    ext_path = WORKSPACE_ROOT / "my-ext"
    fs.directories.add(ext_path)
    manifest_path = ext_path / "winter-ext.toml"
    fs.files[manifest_path] = ""
    config_files[manifest_path] = {"name": "my-ext", "hooks": {"on_env_init": "hooks/init.sh"}}

    hook_path = (ext_path / "hooks" / "init.sh").resolve()
    fs.files[hook_path] = ""
    fs.executables.add(hook_path)
    fs.directories.add(hook_path.parent)

    repos = [StandaloneRepository(name="my-ext", path=ext_path)]
    env_root = WORKSPACE_ROOT / "alpha"

    subprocess = FakeSubprocessRunner(
        popen_responses={str(hook_path): (["doing stuff", "done"], 0)},
    )

    svc = _service(workspace_config, fs, config_files, subprocess)
    ok = svc.run_env_init_hooks(repos, env_root, "alpha", init_reporter)

    assert ok is True
    assert ("my-ext", "doing stuff") in init_reporter.cmd_output
    assert ("my-ext", "done") in init_reporter.cmd_output
    assert any(a[2] == "hook_ran" for a in init_reporter.actions)


def test_run_env_hook_failure_isolated_per_extension(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """One extension's hook failure is caught at its own wrap site — sibling extensions still run,
    the aggregator returns False, and the reporter logs exactly one error for the failing extension."""
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}

    # Extension A: hook exits non-zero (the failure)
    ext_a = WORKSPACE_ROOT / "ext-a"
    fs.directories.add(ext_a)
    manifest_a = ext_a / "winter-ext.toml"
    fs.files[manifest_a] = ""
    config_files[manifest_a] = {"name": "ext-a", "hooks": {"on_env_init": "hooks/a.sh"}}
    hook_a = (ext_a / "hooks" / "a.sh").resolve()
    fs.files[hook_a] = ""
    fs.executables.add(hook_a)
    fs.directories.add(hook_a.parent)

    # Extension B: hook succeeds — must still run despite A's failure
    ext_b = WORKSPACE_ROOT / "ext-b"
    fs.directories.add(ext_b)
    manifest_b = ext_b / "winter-ext.toml"
    fs.files[manifest_b] = ""
    config_files[manifest_b] = {"name": "ext-b", "hooks": {"on_env_init": "hooks/b.sh"}}
    hook_b = (ext_b / "hooks" / "b.sh").resolve()
    fs.files[hook_b] = ""
    fs.executables.add(hook_b)
    fs.directories.add(hook_b.parent)

    repos = [
        StandaloneRepository(name="ext-a", path=ext_a),
        StandaloneRepository(name="ext-b", path=ext_b),
    ]
    subprocess = FakeSubprocessRunner(
        popen_responses={
            str(hook_a): (["broke"], 1),
            str(hook_b): (["ok"], 0),
        },
    )

    svc = _service(workspace_config, fs, config_files, subprocess)
    ok = svc.run_env_init_hooks(repos, WORKSPACE_ROOT / "alpha", "alpha", init_reporter)

    assert ok is False
    # ext-a error logged exactly once
    a_errors = [msg for repo, msg in init_reporter.errors if repo == "ext-a"]
    assert len(a_errors) == 1
    assert "exited with code 1" in a_errors[0]
    # ext-b still ran successfully
    assert ("ext-b", "ok") in init_reporter.cmd_output
    assert any(a[0] == "ext-b" and a[2] == "hook_ran" for a in init_reporter.actions)
