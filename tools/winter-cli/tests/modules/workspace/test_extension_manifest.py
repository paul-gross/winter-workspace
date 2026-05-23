from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeConfigFileReader
from winter_cli.modules.workspace.extension_manifest import (
    DEFAULT_AGENTS_DIRS,
    DEFAULT_SKILLS_DIRS,
    ExtensionManifestLoader,
)
from winter_cli.modules.workspace.models import RepoError, StandaloneRepository

WORKSPACE_ROOT = Path("/ws")


def test_load_returns_defaults_when_manifest_path_is_none() -> None:
    """No manifest on disk → dataclass with defaults and the repo's name as prefix."""
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader({}))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=None)
    assert manifest.prefix == "my-ext"
    assert manifest.skills_dirs == DEFAULT_SKILLS_DIRS
    assert manifest.agents_dirs == DEFAULT_AGENTS_DIRS
    assert manifest.hooks == {}


def test_load_respects_manifest_prefix_and_hooks() -> None:
    """Manifest fields override defaults; non-string hook values are filtered out."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "prefix": "mp",
            "skills_dir": "custom-skills",
            "hooks": {"on_env_init": "scripts/init.sh", "junk": 5},
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.prefix == "mp"
    assert manifest.skills_dirs == ("custom-skills",)
    assert manifest.hooks == {"on_env_init": "scripts/init.sh"}


def test_load_raises_repo_error_on_broken_manifest() -> None:
    """A broken TOML surfaces as `RepoError` so callers can catch at their wrap site."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    reader = FakeConfigFileReader(files={}, broken={manifest_path})
    loader = ExtensionManifestLoader(config_file_reader=reader)
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    with pytest.raises(RepoError, match=r"winter-ext\.toml"):
        loader.load(repo, manifest_path=manifest_path)
