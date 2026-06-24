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
    assert manifest.provides == {}


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


def test_load_parses_provides_table() -> None:
    """`[provides]` is parsed into a dict of slot→entrypoint strings."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "provides": {"service": "workflow/service"},
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.provides == {"service": "workflow/service"}


def test_load_provides_empty_when_missing() -> None:
    """Missing `[provides]` table → empty dict; capability_entrypoint falls back or returns None."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {manifest_path: {}}
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.provides == {}
    assert manifest.capability_entrypoint("service") is None
    assert manifest.capability_entrypoint("unknown") is None


def test_capability_entrypoint_returns_provides_service() -> None:
    """`capability_entrypoint("service")` returns the `provides.service` value when present."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "provides": {"service": "workflow/service"},
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.capability_entrypoint("service") == "workflow/service"


def test_capability_entrypoint_falls_back_to_orchestrate_services() -> None:
    """`capability_entrypoint("service")` falls back to `orchestrate_services` when `provides` has no `service`."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {manifest_path: {"orchestrate_services": "workflow/service"}}
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.capability_entrypoint("service") == "workflow/service"


def test_capability_entrypoint_provides_wins_over_orchestrate_services() -> None:
    """Explicit `provides.service` wins even when `orchestrate_services` is also set."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "provides": {"service": "new/entrypoint"},
            "orchestrate_services": "old/entrypoint",
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.capability_entrypoint("service") == "new/entrypoint"


def test_capability_entrypoint_returns_none_for_unknown_slot() -> None:
    """`capability_entrypoint` with an unknown slot returns None."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "provides": {"service": "workflow/service"},
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.capability_entrypoint("unknown") is None


def test_load_provides_empty_when_non_dict() -> None:
    """A non-dict `provides` (e.g. a bare string) degrades to empty dict; no raise."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "provides": "workflow/service",
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.provides == {}


def test_load_raises_repo_error_on_broken_manifest() -> None:
    """A broken TOML surfaces as `RepoError` so callers can catch at their wrap site."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    reader = FakeConfigFileReader(files={}, broken={manifest_path})
    loader = ExtensionManifestLoader(config_file_reader=reader)
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    with pytest.raises(RepoError, match=r"winter-ext\.toml"):
        loader.load(repo, manifest_path=manifest_path)


def test_load_parses_provision_handlers_with_correct_source() -> None:
    """Valid [[provision.*]] entries are parsed into ExtensionManifest.provision with
    the extension prefix as the source label on each handler."""
    from winter_cli.modules.provision.manifest import ProvisionScope

    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "prefix": "my-ext",
            "provision": {
                "dependency": [
                    {"scope": "feature-environment", "apply": "scripts/install.sh"},
                ],
                "resource": [
                    {
                        "scope": "workspace",
                        "apply": "scripts/create-db.sh",
                        "destroy": "scripts/drop-db.sh",
                        "required_services": ["postgres"],
                    },
                ],
            },
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)

    assert len(manifest.provision) == 2

    dep = manifest.provision[0]
    assert dep.subtarget == "dependency"
    assert dep.scope == ProvisionScope.feature_environment
    assert dep.apply == "scripts/install.sh"
    assert dep.source == "my-ext"
    assert dep.destroy is None
    assert dep.required_services == ()

    res = manifest.provision[1]
    assert res.subtarget == "resource"
    assert res.scope == ProvisionScope.workspace
    assert res.apply == "scripts/create-db.sh"
    assert res.destroy == "scripts/drop-db.sh"
    assert res.source == "my-ext"
    assert res.required_services == ("postgres",)


def test_load_provision_defaults_to_empty_tuple_when_absent() -> None:
    """A manifest without a [provision] table yields an empty provision tuple."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {manifest_path: {}}
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.provision == ()


def test_load_raises_repo_error_on_malformed_provision_entry() -> None:
    """A malformed [[provision.*]] entry raises RepoError so callers can skip the
    extension without breaking unrelated commands."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "provision": {
                "dependency": [
                    {"scope": "bad-scope", "apply": "scripts/install.sh"},
                ],
            },
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    with pytest.raises(RepoError, match=r"winter-ext\.toml"):
        loader.load(repo, manifest_path=manifest_path)


def test_load_provision_source_uses_resolved_prefix() -> None:
    """The source label on each ProvisionHandler is the resolved prefix
    (workspace override > manifest prefix > manifest name > repo dir name)."""
    from winter_cli.modules.provision.manifest import ProvisionScope

    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "manifest-name",
            "provision": {
                "data": [
                    {"scope": "feature-worktree", "apply": "scripts/seed.sh"},
                ],
            },
        }
    }
    # repo.prefix is None so resolution falls through to the manifest `name` field.
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)

    assert manifest.prefix == "manifest-name"
    assert len(manifest.provision) == 1
    assert manifest.provision[0].source == "manifest-name"
    assert manifest.provision[0].scope == ProvisionScope.feature_worktree


# ── [[service]] parsing in ExtensionManifest ──────────────────────────────────


def test_load_service_defs_defaults_to_empty_tuple_when_absent() -> None:
    """A manifest without a [[service]] array yields an empty service_defs tuple."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {manifest_path: {}}
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.service_defs == ()


def test_load_service_defs_parses_valid_entries() -> None:
    """Valid [[service]] entries are parsed into ExtServiceDef tuples."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "prefix": "my-ext",
            "service": [
                {"name": "api", "scope": "feature-environment", "command": "uvicorn"},
                {"name": "db", "scope": "workspace"},
            ],
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)

    assert len(manifest.service_defs) == 2
    api = manifest.service_defs[0]
    assert api.name == "api"
    assert api.scope == "feature-environment"
    assert api.command == "uvicorn"
    assert api.source == "my-ext"

    db = manifest.service_defs[1]
    assert db.name == "db"
    assert db.scope == "workspace"
    assert db.source == "my-ext"


def test_load_service_defs_raises_repo_error_on_malformed_entry() -> None:
    """A malformed [[service]] entry (unknown key) raises RepoError."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "service": [{"name": "api", "unknown_key": "bad"}],
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    with pytest.raises(RepoError, match=r"winter-ext\.toml"):
        loader.load(repo, manifest_path=manifest_path)


def test_load_service_defs_source_uses_resolved_prefix() -> None:
    """The source label on each ExtServiceDef is the resolved prefix."""
    manifest_path = WORKSPACE_ROOT / "my-ext" / "winter-ext.toml"
    config_files = {
        manifest_path: {
            "name": "resolved-name",
            "service": [{"name": "svc"}],
        }
    }
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files))
    repo = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")

    manifest = loader.load(repo, manifest_path=manifest_path)
    assert manifest.service_defs[0].source == "resolved-name"
