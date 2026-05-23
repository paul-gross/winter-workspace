from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import (
    FakeConfigFileReader,
    FakeFilesystem,
    FakeGitRepository,
    FakeSubprocessRunner,
)
from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.modules.workspace.extensions import ExtensionService
from winter_cli.modules.workspace.prune_service import PruneOrphan, PruneService
from winter_cli.modules.workspace.repository_factory import RepositoryFactory

WORKSPACE_ROOT = Path("/ws")
PROJECTS_DIR = WORKSPACE_ROOT / "projects"


@pytest.fixture
def workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_root=WORKSPACE_ROOT,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
        project_repos=[
            ProjectRepositoryConfig(name="kept", url="git@example.com:org/kept.git"),
        ],
    )


def _service(
    workspace_config: WorkspaceConfig,
    fs: FakeFilesystem,
    git: FakeGitRepository | None = None,
) -> PruneService:
    git = git or FakeGitRepository()
    # ExtensionService is only used here for finalize_excludes (re-aggregation),
    # which the prune tests don't exercise; pass in fakes for completeness.
    ext_svc = ExtensionService(
        workspace_config,
        fs=fs,
        config_file_reader=FakeConfigFileReader({}),
        subprocess_runner=FakeSubprocessRunner(),
    )
    return PruneService(
        config=workspace_config,
        repo_factory=RepositoryFactory(workspace_config),
        extension_svc=ext_svc,
        fs=fs,
        git_repo=git,
    )


def test_find_orphans_returns_empty_when_projects_dir_missing(workspace_config: WorkspaceConfig) -> None:
    fs = FakeFilesystem()
    svc = _service(workspace_config, fs)
    assert svc.find_orphans() == []


def test_find_orphans_flags_undeclared_clean_clone_as_safe(workspace_config: WorkspaceConfig) -> None:
    """An undeclared clone with a clean tree and no linked worktrees is safe to remove."""
    orphan_path = PROJECTS_DIR / "ghost"
    fs = FakeFilesystem(
        directories=[PROJECTS_DIR, orphan_path],
        files={orphan_path / ".git" / "HEAD": "ref: refs/heads/main\n"},
    )
    git = FakeGitRepository()
    git.clean_worktrees.add(orphan_path)
    svc = _service(workspace_config, fs, git)

    orphans = svc.find_orphans()
    project_orphans = [o for o in orphans if o.kind == "project_clone"]
    assert len(project_orphans) == 1
    assert project_orphans[0].path == orphan_path
    assert project_orphans[0].safe_to_remove is True


def test_find_orphans_flags_dirty_clone_as_unsafe(workspace_config: WorkspaceConfig) -> None:
    orphan_path = PROJECTS_DIR / "dirty"
    fs = FakeFilesystem(
        directories=[PROJECTS_DIR, orphan_path],
        files={orphan_path / ".git" / "HEAD": "ref: refs/heads/main\n"},
    )
    git = FakeGitRepository()  # nothing added to clean_worktrees → dirty
    svc = _service(workspace_config, fs, git)

    [orphan] = [o for o in svc.find_orphans() if o.kind == "project_clone"]
    assert orphan.safe_to_remove is False
    assert "uncommitted or untracked" in orphan.notes


def test_find_orphans_flags_clone_with_linked_worktrees_as_unsafe(workspace_config: WorkspaceConfig) -> None:
    orphan_path = PROJECTS_DIR / "linked"
    linked_wt_dir = orphan_path / ".git" / "worktrees" / "alpha"
    fs = FakeFilesystem(
        directories=[PROJECTS_DIR, orphan_path, orphan_path / ".git" / "worktrees", linked_wt_dir],
        files={orphan_path / ".git" / "HEAD": ""},
    )
    git = FakeGitRepository()
    git.clean_worktrees.add(orphan_path)  # clean — still blocked by linked worktrees
    svc = _service(workspace_config, fs, git)

    [orphan] = [o for o in svc.find_orphans() if o.kind == "project_clone"]
    assert orphan.safe_to_remove is False
    assert "linked worktrees" in orphan.notes


def test_remove_orphan_deletes_safe_clone(workspace_config: WorkspaceConfig) -> None:
    orphan_path = PROJECTS_DIR / "ghost"
    fs = FakeFilesystem(
        directories=[PROJECTS_DIR, orphan_path],
        files={orphan_path / ".git" / "HEAD": ""},
    )
    git = FakeGitRepository()
    git.clean_worktrees.add(orphan_path)
    svc = _service(workspace_config, fs, git)

    [orphan] = svc.find_orphans()
    svc.remove_orphan(orphan)
    assert not fs.exists(orphan_path)


def test_remove_orphan_refuses_unsafe(workspace_config: WorkspaceConfig) -> None:
    fs = FakeFilesystem()
    svc = _service(workspace_config, fs)
    unsafe = PruneOrphan(kind="project_clone", path=WORKSPACE_ROOT / "x", safe_to_remove=False, notes="dirty")
    with pytest.raises(RuntimeError, match="unsafe orphan"):
        svc.remove_orphan(unsafe)


def test_find_broken_symlinks_under_claude_dirs(workspace_config: WorkspaceConfig) -> None:
    """Broken symlinks under .claude/{skills,agents} are flagged as safe-to-remove orphans."""
    claude_skills = WORKSPACE_ROOT / ".claude" / "skills"
    fs = FakeFilesystem(directories=[claude_skills])
    fs.symlinks[claude_skills / "ext-removed"] = Path("../../ext-removed/skills/x")
    svc = _service(workspace_config, fs)

    orphans = svc.find_orphans()
    broken = [o for o in orphans if o.kind == "broken_symlink"]
    assert len(broken) == 1
    assert broken[0].safe_to_remove is True
