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


@pytest.fixture
def workspace_config_none() -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=WORKSPACE_ROOT,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.none,
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


# ---------------------------------------------------------------------------
# Phase-3: winter-config block tests
# ---------------------------------------------------------------------------

EXCLUDE_PATH = WORKSPACE_ROOT / ".git" / "info" / "exclude"
WINTER_CONFIG_BEGIN = "# >>> winter-config (managed by winter)"
WINTER_CONFIG_END = "# <<< winter-config"
WINTER_CONFIG_BODY = ".winter/config/**/*.local.*"


def test_winter_config_block_is_written(workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter) -> None:
    """finalize_excludes writes the winter-config block with the correct body line."""
    fs = FakeFilesystem(directories=[WORKSPACE_ROOT / ".git" / "info"])
    svc = _service(workspace_config, fs, {})

    ok = svc.finalize_excludes([], init_reporter)
    assert ok is True

    content = fs.files[EXCLUDE_PATH]
    assert WINTER_CONFIG_BEGIN in content
    assert WINTER_CONFIG_BODY in content
    assert WINTER_CONFIG_END in content


def test_winter_config_block_is_idempotent(workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter) -> None:
    """A second call to finalize_excludes leaves the winter-config block unchanged."""
    fs = FakeFilesystem(directories=[WORKSPACE_ROOT / ".git" / "info"])
    svc = _service(workspace_config, fs, {})

    svc.finalize_excludes([], init_reporter)
    content_after_first = fs.files[EXCLUDE_PATH]

    svc.finalize_excludes([], init_reporter)
    content_after_second = fs.files[EXCLUDE_PATH]

    assert content_after_first == content_after_second
    assert content_after_second.count(WINTER_CONFIG_BEGIN) == 1


def test_winter_config_block_written_in_none_mode(
    workspace_config_none: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """The winter-config block is written even when adopt_extensions=none."""
    fs = FakeFilesystem(directories=[WORKSPACE_ROOT / ".git" / "info"])
    svc = _service(workspace_config_none, fs, {})

    ok = svc.finalize_excludes([], init_reporter)
    assert ok is True

    content = fs.files[EXCLUDE_PATH]
    assert WINTER_CONFIG_BEGIN in content
    assert WINTER_CONFIG_BODY in content


def test_orphan_stripper_does_not_remove_winter_config(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """The orphan-stripper never removes the winter-config block, even with empty eligible_names."""
    # Pre-seed the exclude file with the winter-config block already present.
    existing = "\n".join([WINTER_CONFIG_BEGIN, WINTER_CONFIG_BODY, WINTER_CONFIG_END, ""])
    fs = FakeFilesystem(
        files={EXCLUDE_PATH: existing},
        directories=[WORKSPACE_ROOT / ".git" / "info"],
    )
    svc = _service(workspace_config, fs, {})

    # Call with no repos → eligible_names is empty, so orphan stripper sees winter-config
    # as a candidate. It must be spared.
    ok = svc.finalize_excludes([], init_reporter)
    assert ok is True

    content = fs.files[EXCLUDE_PATH]
    assert WINTER_CONFIG_BEGIN in content
    assert WINTER_CONFIG_BODY in content
