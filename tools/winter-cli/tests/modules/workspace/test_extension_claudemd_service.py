from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeFilesystem, FakeInitReporter
from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.modules.workspace.extension_claudemd_service import ExtensionClaudemdService
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


def _seed_extension_with_index(fs: FakeFilesystem, name: str) -> StandaloneRepository:
    """Plant an extension repo with an index.md so claudemd treats it as eligible."""
    ext_path = WORKSPACE_ROOT / name
    fs.directories.add(ext_path)
    fs.files[ext_path / "index.md"] = "# index\n"
    return StandaloneRepository(name=name, path=ext_path)


def test_finalize_claudemd_writes_imports_for_eligible_repos(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    fs = FakeFilesystem()
    ext_a = _seed_extension_with_index(fs, "ext-a")
    ext_b = _seed_extension_with_index(fs, "ext-b")
    svc = ExtensionClaudemdService(config=workspace_config, fs=fs)

    ok = svc.finalize_claudemd([ext_a, ext_b], init_reporter)
    assert ok is True

    winter_path = WORKSPACE_ROOT / "CLAUDE.winter.md"
    content = fs.files[winter_path]
    assert "**ext-a**" in content
    assert "@ext-a/index.md" in content
    assert "**ext-b**" in content


def test_finalize_claudemd_skips_repos_without_index_md(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """Repos without an `index.md` at the root are excluded entirely."""
    fs = FakeFilesystem()
    ext_path = WORKSPACE_ROOT / "no-index"
    fs.directories.add(ext_path)
    no_index_repo = StandaloneRepository(name="no-index", path=ext_path)
    svc = ExtensionClaudemdService(config=workspace_config, fs=fs)

    ok = svc.finalize_claudemd([no_index_repo], init_reporter)
    assert ok is True

    winter_path = WORKSPACE_ROOT / "CLAUDE.winter.md"
    # No eligible extensions and the file didn't exist — nothing was written.
    assert winter_path not in fs.files
