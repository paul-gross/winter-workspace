from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tests.conftest import FakeInitReporter
from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.modules.workspace.extensions import ExtensionService
from winter_cli.modules.workspace.models import StandaloneRepository


@pytest.fixture
def workspace_config(tmp_path: Path) -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=tmp_path,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
    )


@pytest.fixture
def service(workspace_config: WorkspaceConfig) -> ExtensionService:
    return ExtensionService(workspace_config)


def _make_extension(workspace_root: Path, name: str = "my-ext") -> StandaloneRepository:
    """Create a tiny extension on disk: winter-ext.toml + one skill + one agent."""
    ext_path = workspace_root / name
    ext_path.mkdir()
    (ext_path / "winter-ext.toml").write_text(f'name = "{name}"\n')

    # One skill directory containing a SKILL.md without a `name` frontmatter field.
    skill_dir = ext_path / "skills" / "do-thing"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        dedent(
            """
            ---
            description: An example skill
            ---

            # do-thing

            Body of the skill.
            """
        ).lstrip()
    )

    # One flat agent file.
    agents_dir = ext_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "reviewer.md").write_text("# reviewer\n")

    return StandaloneRepository(name=name, path=ext_path)


def test_process_symlinks_skills_and_agents(
    tmp_path: Path,
    service: ExtensionService,
    init_reporter: FakeInitReporter,
) -> None:
    ext = _make_extension(tmp_path)

    ok = service.process(ext, init_reporter)

    assert ok is True
    # Skill directory linked under prefix-<dirname>.
    skill_link = tmp_path / ".claude" / "skills" / "my-ext-do-thing"
    assert skill_link.is_symlink()
    assert skill_link.resolve() == (ext.path / "skills" / "do-thing").resolve()

    # Agent file linked under prefix-<filename> (preserving .md).
    agent_link = tmp_path / ".claude" / "agents" / "my-ext-reviewer.md"
    assert agent_link.is_symlink()
    assert agent_link.resolve() == (ext.path / "agents" / "reviewer.md").resolve()

    actions = [(a[0], a[2]) for a in init_reporter.actions]
    assert ("my-ext", "extension_installed") in actions


def test_process_skips_when_adopt_mode_is_none(tmp_path: Path, init_reporter: FakeInitReporter) -> None:
    config = WorkspaceConfig(
        workspace_root=tmp_path,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.none,
    )
    ext = _make_extension(tmp_path)

    assert ExtensionService(config).process(ext, init_reporter) is True
    # No symlinks created.
    assert not (tmp_path / ".claude" / "skills" / "my-ext-do-thing").exists()


def test_process_skips_in_winter_mode_when_manifest_missing(
    tmp_path: Path, service: ExtensionService, init_reporter: FakeInitReporter
) -> None:
    """`adopt_extensions = winter` ignores repos that don't declare winter-ext.toml."""
    ext_path = tmp_path / "vanilla"
    ext_path.mkdir()
    (ext_path / "skills" / "do-thing").mkdir(parents=True)
    (ext_path / "skills" / "do-thing" / "SKILL.md").write_text("# skill\n")
    ext = StandaloneRepository(name="vanilla", path=ext_path)

    assert service.process(ext, init_reporter) is True
    assert not (tmp_path / ".claude" / "skills" / "vanilla-do-thing").exists()


def test_process_rejects_skill_md_with_name_frontmatter(
    tmp_path: Path, service: ExtensionService, init_reporter: FakeInitReporter
) -> None:
    """In strict (winter) mode, SKILL.md must not override the directory name."""
    ext = _make_extension(tmp_path)
    skill_md = ext.path / "skills" / "do-thing" / "SKILL.md"
    skill_md.write_text(
        dedent(
            """
            ---
            name: override-name
            description: An example skill
            ---

            Body.
            """
        ).lstrip()
    )

    assert service.process(ext, init_reporter) is False
    error_messages = [error for _, error in init_reporter.errors]
    assert any("name: override-name" in msg for msg in error_messages)
