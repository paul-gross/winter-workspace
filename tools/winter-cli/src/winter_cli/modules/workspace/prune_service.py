from __future__ import annotations

import dataclasses
import re
import shutil
import subprocess
from pathlib import Path

from winter_cli.config.models import WorkspaceConfig
from winter_cli.modules.workspace.extensions import ExtensionService
from winter_cli.modules.workspace.init_reporter import IInitReporter
from winter_cli.modules.workspace.repository_factory import RepositoryFactory


_BLOCK_BEGIN_RE = re.compile(r"^# >>> ([^/]+?) \(managed by winter\)$")
_BLOCK_PATH_RE = re.compile(r"^/(.+?)/?$")


@dataclasses.dataclass
class PruneOrphan:
    kind: str
    """One of: 'project_clone', 'standalone_clone', 'broken_symlink'."""

    path: Path
    """Absolute path of the orphan on disk."""

    safe_to_remove: bool
    """False when removing would discard work or break worktrees."""

    notes: str
    """Empty when safe; otherwise the reason it's blocked."""


class PruneService:
    """Detects and removes disk state for repos no longer in the workspace config."""

    def __init__(
        self,
        config: WorkspaceConfig,
        repo_factory: RepositoryFactory,
        extension_svc: ExtensionService,
    ) -> None:
        self._config = config
        self._repo_factory = repo_factory
        self._extension_svc = extension_svc

    def find_orphans(self) -> list[PruneOrphan]:
        orphans: list[PruneOrphan] = []
        orphans.extend(self._find_orphan_project_clones())
        orphans.extend(self._find_orphan_standalone_clones())
        orphans.extend(self._find_broken_symlinks())
        return orphans

    def remove_orphan(self, orphan: PruneOrphan) -> None:
        if not orphan.safe_to_remove:
            raise RuntimeError(f"refusing to remove unsafe orphan: {orphan.path} ({orphan.notes})")
        if orphan.path.is_symlink():
            orphan.path.unlink()
        elif orphan.path.is_dir():
            shutil.rmtree(orphan.path)
        elif orphan.path.exists():
            orphan.path.unlink()

    def reaggregate_excludes(self, reporter: IInitReporter) -> bool:
        return self._extension_svc.finalize_excludes(self._repo_factory.get_standalone_repos(), reporter)

    # ── detection ────────────────────────────────────────────────────────

    def _find_orphan_project_clones(self) -> list[PruneOrphan]:
        projects_dir = self._config.workspace_root / "projects"
        if not projects_dir.is_dir():
            return []
        declared = {repo.name for repo in self._repo_factory.get_project_repos()}
        orphans: list[PruneOrphan] = []
        for entry in sorted(projects_dir.iterdir()):
            if not entry.is_dir() or entry.name in declared:
                continue
            safe, notes = self._project_clone_safety(entry)
            orphans.append(PruneOrphan(
                kind="project_clone",
                path=entry,
                safe_to_remove=safe,
                notes=notes,
            ))
        return orphans

    def _find_orphan_standalone_clones(self) -> list[PruneOrphan]:
        exclude_path = self._config.workspace_root / ".git" / "info" / "exclude"
        if not exclude_path.exists():
            return []
        try:
            content = exclude_path.read_text()
        except OSError:
            return []

        eligible = {repo.name for repo in self._repo_factory.get_standalone_repos()}
        orphans: list[PruneOrphan] = []
        seen_paths: set[Path] = set()

        for block_name, block_lines in self._iter_managed_blocks(content):
            if block_name in eligible:
                continue
            for line in block_lines:
                m = _BLOCK_PATH_RE.match(line.strip())
                if not m:
                    continue
                rel = m.group(1)
                if rel.startswith(".claude/"):
                    continue
                if rel == "projects":
                    continue
                path = (self._config.workspace_root / rel).resolve()
                if path in seen_paths or not path.exists():
                    continue
                seen_paths.add(path)
                safe, notes = self._project_clone_safety(path) if (path / ".git").exists() else (True, "")
                orphans.append(PruneOrphan(
                    kind="standalone_clone",
                    path=path,
                    safe_to_remove=safe,
                    notes=notes,
                ))
        return orphans

    def _find_broken_symlinks(self) -> list[PruneOrphan]:
        roots = [
            self._config.workspace_root / ".claude" / "skills",
            self._config.workspace_root / ".claude" / "agents",
        ]
        orphans: list[PruneOrphan] = []
        for root in roots:
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir()):
                if entry.is_symlink() and not entry.exists():
                    orphans.append(PruneOrphan(
                        kind="broken_symlink",
                        path=entry,
                        safe_to_remove=True,
                        notes="",
                    ))
        return orphans

    @staticmethod
    def _iter_managed_blocks(content: str):
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            m = _BLOCK_BEGIN_RE.match(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1)
            end_marker = f"# <<< {name}"
            j = i + 1
            block_lines: list[str] = []
            while j < len(lines) and lines[j] != end_marker:
                block_lines.append(lines[j])
                j += 1
            yield name, block_lines
            i = j + 1

    @staticmethod
    def _project_clone_safety(path: Path) -> tuple[bool, str]:
        if not (path / ".git").exists():
            return False, "not a git clone (delete by hand if intentional)"
        worktrees_dir = path / ".git" / "worktrees"
        if worktrees_dir.is_dir() and any(worktrees_dir.iterdir()):
            return False, "has linked worktrees"
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False, "could not run git status"
        if result.returncode != 0:
            return False, "git status failed"
        if result.stdout.strip():
            return False, "uncommitted or untracked changes"
        return True, ""
