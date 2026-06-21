from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import (
    FakeConfigFileReader,
    FakeFilesystem,
    FakeInitReporter,
)
from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.modules.workspace.extension_manifest import ExtensionManifestLoader
from winter_cli.modules.workspace.extension_symlink_service import ExtensionSymlinkService
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
    config_files: dict[Path, dict] | None = None,
) -> ExtensionSymlinkService:
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(config_files or {}))
    return ExtensionSymlinkService(
        config=workspace_config,
        fs=fs,
        manifest_loader=loader,
    )


def _seed_extension(
    fs: FakeFilesystem,
    config_files: dict[Path, dict],
    name: str = "my-ext",
    *,
    skip_skill: bool = False,
    skill_frontmatter_name: str | None = None,
) -> StandaloneRepository:
    """Plant a tiny extension in the fake fs: winter-ext.toml + skill dir + agent file."""
    ext_path = WORKSPACE_ROOT / name
    fs.directories.add(ext_path)

    manifest_path = ext_path / "winter-ext.toml"
    fs.files[manifest_path] = ""  # presence only; reader returns dict below
    config_files[manifest_path] = {"name": name}

    seeded_dirs: list[Path] = [ext_path]
    if not skip_skill:
        skill_dir = ext_path / "skills" / "do-thing"
        fs.directories.add(skill_dir)
        seeded_dirs.append(skill_dir)
        skill_md = skill_dir / "SKILL.md"
        if skill_frontmatter_name is None:
            fs.files[skill_md] = "---\ndescription: An example skill\n---\n\n# do-thing\n"
        else:
            fs.files[skill_md] = f"---\nname: {skill_frontmatter_name}\ndescription: x\n---\n"

    agents_dir = ext_path / "agents"
    fs.directories.add(agents_dir)
    seeded_dirs.append(agents_dir)
    fs.files[agents_dir / "reviewer.md"] = "# reviewer\n"

    # Materialize parent dirs so iterdir() at any ancestor sees children.
    for p in seeded_dirs:
        for parent in p.parents:
            fs.directories.add(parent)

    return StandaloneRepository(name=name, path=ext_path)


def test_process_symlinks_skills_and_agents(workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter) -> None:
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    ext = _seed_extension(fs, config_files)
    svc = _service(workspace_config, fs, config_files)

    ok = svc.process(ext, init_reporter)

    assert ok is True

    # Skill symlink created under .claude/skills/<prefix>-<dirname>
    skill_link = WORKSPACE_ROOT / ".claude" / "skills" / "my-ext-do-thing"
    assert fs.is_symlink(skill_link)

    # And mirrored into .codex/skills so Codex can load it too.
    codex_skill_link = WORKSPACE_ROOT / ".codex" / "skills" / "my-ext-do-thing"
    assert fs.is_symlink(codex_skill_link)

    # Agents are Claude-only: no .codex/agents projection.
    assert not fs.is_symlink(WORKSPACE_ROOT / ".codex" / "agents" / "my-ext-reviewer.md")

    # Agent symlink created under .claude/agents/<prefix>-<filename>
    agent_link = WORKSPACE_ROOT / ".claude" / "agents" / "my-ext-reviewer.md"
    assert fs.is_symlink(agent_link)

    actions = [(a[0], a[2]) for a in init_reporter.actions]
    assert ("my-ext", "extension_installed") in actions


def test_process_skips_when_adopt_mode_is_none(init_reporter: FakeInitReporter) -> None:
    config = WorkspaceConfig(
        workspace_root=WORKSPACE_ROOT,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.none,
    )
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    ext = _seed_extension(fs, config_files)
    svc = _service(config, fs, config_files)

    assert svc.process(ext, init_reporter) is True
    assert not fs.is_symlink(WORKSPACE_ROOT / ".claude" / "skills" / "my-ext-do-thing")


def test_process_skips_in_winter_mode_when_manifest_missing(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """`adopt_extensions = winter` ignores repos that don't declare winter-ext.toml."""
    fs = FakeFilesystem()
    ext_path = WORKSPACE_ROOT / "vanilla"
    fs.directories.update({ext_path, ext_path / "skills", ext_path / "skills" / "do-thing"})
    fs.files[ext_path / "skills" / "do-thing" / "SKILL.md"] = "# skill\n"
    ext = StandaloneRepository(name="vanilla", path=ext_path)
    svc = _service(workspace_config, fs)

    assert svc.process(ext, init_reporter) is True
    assert not fs.is_symlink(WORKSPACE_ROOT / ".claude" / "skills" / "vanilla-do-thing")


def test_process_rejects_skill_md_with_name_frontmatter(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    _seed_extension(fs, config_files, skill_frontmatter_name="override-name")
    ext = StandaloneRepository(name="my-ext", path=WORKSPACE_ROOT / "my-ext")
    svc = _service(workspace_config, fs, config_files)

    assert svc.process(ext, init_reporter) is False
    error_messages = [error for _, error in init_reporter.errors]
    assert any("name: override-name" in msg for msg in error_messages)


def test_process_skips_readme_and_docs_subdir_in_agents(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """`agents/README.md` and `agents/docs/` (no AGENT.md) must not get symlinked."""
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    ext = _seed_extension(fs, config_files)
    agents_dir = ext.path / "agents"
    fs.files[agents_dir / "README.md"] = "# Agent conventions\n"
    docs_dir = agents_dir / "docs"
    fs.directories.add(docs_dir)
    fs.files[docs_dir / "default-principles.md"] = "# principles\n"
    svc = _service(workspace_config, fs, config_files)

    assert svc.process(ext, init_reporter) is True

    agents_target = WORKSPACE_ROOT / ".claude" / "agents"
    assert fs.is_symlink(agents_target / "my-ext-reviewer.md")
    assert not fs.is_symlink(agents_target / "my-ext-README.md")
    assert not fs.is_symlink(agents_target / "my-ext-docs")


def test_process_symlinks_nested_agent_directory_with_marker(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """Directories carrying `AGENT.md` are nested agents and get a directory symlink."""
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    ext = _seed_extension(fs, config_files)
    nested = ext.path / "agents" / "nested"
    fs.directories.add(nested)
    fs.files[nested / "AGENT.md"] = "---\n---\n# nested\n"
    svc = _service(workspace_config, fs, config_files)

    assert svc.process(ext, init_reporter) is True
    assert fs.is_symlink(WORKSPACE_ROOT / ".claude" / "agents" / "my-ext-nested")


def test_process_prunes_stale_prefixed_symlinks(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """A `<prefix>-*` symlink whose source entry no longer exists is removed.

    Captures the historical `wf-blizzard` case: a directory symlink left
    behind after the source `agents/blizzard/` was deleted upstream.
    Symlinks owned by a different prefix must survive.
    """
    fs = FakeFilesystem()
    config_files: dict[Path, dict] = {}
    ext = _seed_extension(fs, config_files)

    agents_target = WORKSPACE_ROOT / ".claude" / "agents"
    fs.directories.add(agents_target)
    fs.symlinks[agents_target / "my-ext-blizzard"] = Path("../../my-ext/agents/blizzard")
    fs.symlinks[agents_target / "other-ext-keep.md"] = Path("../../other-ext/agents/keep.md")

    svc = _service(workspace_config, fs, config_files)

    assert svc.process(ext, init_reporter) is True
    assert not fs.is_symlink(agents_target / "my-ext-blizzard")
    assert fs.is_symlink(agents_target / "other-ext-keep.md")
    assert fs.is_symlink(agents_target / "my-ext-reviewer.md")


def test_process_wrap_catches_manifest_read_error(
    workspace_config: WorkspaceConfig, init_reporter: FakeInitReporter
) -> None:
    """A broken winter-ext.toml raises from the manifest loader and is caught at process()'s wrap site."""
    fs = FakeFilesystem()
    ext_path = WORKSPACE_ROOT / "broken-ext"
    fs.directories.add(ext_path)
    manifest_path = ext_path / "winter-ext.toml"
    fs.files[manifest_path] = ""

    # FakeConfigFileReader registers the path as "broken" so .load() raises ConfigFileReadError.
    reader = FakeConfigFileReader(files={}, broken={manifest_path})
    svc = ExtensionSymlinkService(
        config=workspace_config,
        fs=fs,
        manifest_loader=ExtensionManifestLoader(config_file_reader=reader),
    )

    ext = StandaloneRepository(name="broken-ext", path=ext_path)
    ok = svc.process(ext, init_reporter)

    assert ok is False
    errors = [msg for repo, msg in init_reporter.errors if repo == "broken-ext"]
    assert len(errors) == 1
    assert "winter-ext.toml" in errors[0]
