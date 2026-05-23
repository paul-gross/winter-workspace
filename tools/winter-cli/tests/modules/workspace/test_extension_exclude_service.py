from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import (
    FakeConfigFileReader,
    FakeFilesystem,
    FakeInitReporter,
)
from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.modules.workspace.extension_exclude_service import ExtensionExcludeService
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
) -> ExtensionExcludeService:
    return ExtensionExcludeService(
        config=workspace_config,
        fs=fs,
        manifest_loader=ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files)),
    )


def _seed_minimal_extension(fs: FakeFilesystem, config_files: dict[Path, dict], name: str) -> None:
    """Plant just the manifest under WORKSPACE_ROOT/<name>/ so exclude resolution succeeds."""
    ext_path = WORKSPACE_ROOT / name
    fs.directories.add(ext_path)
    manifest_path = ext_path / "winter-ext.toml"
    fs.files[manifest_path] = ""
    config_files[manifest_path] = {"name": name}


def test_finalize_excludes_writes_one_block_per_extension(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    fs = FakeFilesystem(directories=[WORKSPACE_ROOT / ".git" / "info"])
    config_files: dict[Path, dict] = {}
    _seed_minimal_extension(fs, config_files, "ext-a")
    _seed_minimal_extension(fs, config_files, "ext-b")
    repos = [
        StandaloneRepository(name="ext-a", path=WORKSPACE_ROOT / "ext-a"),
        StandaloneRepository(name="ext-b", path=WORKSPACE_ROOT / "ext-b"),
    ]
    svc = _service(workspace_config, fs, config_files)

    ok = svc.finalize_excludes(repos, init_reporter)
    assert ok is True

    exclude_path = WORKSPACE_ROOT / ".git" / "info" / "exclude"
    content = fs.files[exclude_path]
    assert "# >>> ext-a (managed by winter)" in content
    assert "# >>> ext-b (managed by winter)" in content
    assert "/ext-a/" in content
    assert ".claude/skills/ext-a-*" in content
