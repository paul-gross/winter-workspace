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
    assert manifest.doctor is None
    assert manifest.lint == ()
    assert manifest.orchestrate_services is None
    assert manifest.requires == ()


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


def test_load_parses_doctor_script_path() -> None:
    """`doctor` is a single relative script path; empty / non-string falls back to None."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "doctor": "scripts/doctor.sh",
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.doctor == "scripts/doctor.sh"


def test_load_ignores_non_string_doctor_value() -> None:
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "doctor": 42,
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.doctor is None


def test_load_parses_orchestrate_services_entrypoint() -> None:
    """`orchestrate_services` is a single relative entrypoint path; empty / non-string falls back to None."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {manifest_path: {"orchestrate_services": "workflow/service"}}
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    assert loader.load(repo, manifest_path=manifest_path).orchestrate_services == "workflow/service"


def test_load_orchestrate_services_defaults_to_none() -> None:
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {manifest_path: {"orchestrate_services": ""}}
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    assert loader.load(repo, manifest_path=manifest_path).orchestrate_services is None


def test_load_coerces_lint_to_a_tuple() -> None:
    """`lint` accepts a single path or a list; both become a tuple of non-empty strings."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    loader = ExtensionManifestLoader(
        config_file_reader=FakeConfigFileReader(
            {
                manifest_path: {"lint": "scripts/lint.sh"},
            }
        )
    )
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")
    assert loader.load(repo, manifest_path=manifest_path).lint == ("scripts/lint.sh",)

    loader_list = ExtensionManifestLoader(
        config_file_reader=FakeConfigFileReader(
            {
                manifest_path: {"lint": ["a.py", "b.py", 7]},
            }
        )
    )
    assert loader_list.load(repo, manifest_path=manifest_path).lint == ("a.py", "b.py")


def test_load_parses_requires_list() -> None:
    """`requires` is a list of module-name strings; preserved in order."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "requires": ["winter-product", "winter-github"],
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.requires == ("winter-product", "winter-github")


def test_load_filters_non_string_and_empty_requires_entries() -> None:
    """Non-string and empty entries are dropped; the rest survive in order."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "requires": ["winter-product", 5, "", "winter-github"],
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.requires == ("winter-product", "winter-github")


def test_load_ignores_non_list_requires_value() -> None:
    """A non-list `requires` (e.g. a bare string) falls back to empty."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "requires": "winter-product",
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.requires == ()


def test_load_raises_repo_error_on_broken_manifest() -> None:
    """A broken TOML surfaces as `RepoError` so callers can catch at their wrap site."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    reader = FakeConfigFileReader(files={}, broken={manifest_path})
    loader = ExtensionManifestLoader(config_file_reader=reader)
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    with pytest.raises(RepoError, match=r"winter-ext\.toml"):
        loader.load(repo, manifest_path=manifest_path)
