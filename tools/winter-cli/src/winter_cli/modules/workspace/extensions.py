from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.modules.workspace.init_reporter import IInitReporter
from winter_cli.modules.workspace.internal.managed_block import (
    GITIGNORE_BEGIN,
    GITIGNORE_END,
    replace_or_append_block,
    strip_block,
)
from winter_cli.modules.workspace.internal.read_workspace_repository import resolve_worktree_index
from winter_cli.modules.workspace.models import StandaloneRepository

EXT_MANIFEST = "winter-ext.toml"
DEFAULT_SKILLS_DIRS = ("skills", ".claude/skills")
DEFAULT_AGENTS_DIRS = ("agents", ".claude/agents")

PORT_BASE = 4000
PORT_STEP = 100

HOOK_ON_WORKTREE_INIT = "on_worktree_init"

CLAUDEMD_BLOCK_NAME = "winter-extensions"
CLAUDEMD_INDEX_FILENAME = "index.md"

# Workspaces commit a stable `# Winter Extensions` section in CLAUDE.md that
# imports `@CLAUDE.winter.md`; this CLI only writes the imported file. The
# file is gitignored so init runs don't dirty the workspace.
CLAUDEMD_WINTER_FILENAME = "CLAUDE.winter.md"


@dataclass(frozen=True)
class ExtensionManifest:
    """Resolved extension settings for a single standalone repo.

    `prefix` is the final symlink prefix after applying overrides:
    workspace config `prefix` > manifest `prefix` > manifest `name` > repo dir name.

    `skills_dirs` and `agents_dirs` are ordered candidate paths; processing uses
    the first one that exists. The defaults try the winter convention
    (top-level `skills/`/`agents/`) and then the Claude Code convention
    (`.claude/skills/`/`.claude/agents/`), so vanilla Claude Code repos can be
    adopted as extensions without modification.

    `hooks` maps hook names (e.g. `on_worktree_init`) to executable script paths
    relative to the extension's repo root. Hooks let an extension contribute
    setup steps that don't fit the symlink-skills/agents model — for example,
    dropping additional files into a worktree or running provisioning commands.
    """
    prefix: str
    skills_dirs: tuple[str, ...]
    agents_dirs: tuple[str, ...]
    hooks: dict[str, str] = field(default_factory=dict)


class ExtensionService:
    """Processes standalone repos as winter extensions.

    For each repo, decides whether it should contribute skills/agents (per
    `adopt_extensions` mode and the presence of `winter-ext.toml`), validates
    SKILL.md frontmatter conforms to the prefix-by-directory convention, and
    creates per-entry symlinks under `.claude/skills/<prefix>-<dir>` and
    `.claude/agents/<prefix>-<dir>`. After all standalones are reconciled,
    `finalize_excludes` writes a marker-bracketed block per extension to the
    workspace `.git/info/exclude`.
    """

    def __init__(self, config: WorkspaceConfig) -> None:
        self._config = config

    def process(
        self,
        repo: StandaloneRepository,
        reporter: IInitReporter,
    ) -> bool:
        mode = self._config.adopt_extensions
        if mode == AdoptExtensions.none:
            return True

        manifest_path = repo.path / EXT_MANIFEST
        manifest_present = manifest_path.is_file()

        if mode == AdoptExtensions.winter and not manifest_present:
            return True

        manifest = self._load_manifest(repo, manifest_path if manifest_present else None, reporter)
        if manifest is None:
            return False

        skills_root = self._resolve_existing_dir(repo.path, manifest.skills_dirs)
        agents_root = self._resolve_existing_dir(repo.path, manifest.agents_dirs)

        if not self._validate_frontmatter(repo, skills_root, reporter, strict=mode == AdoptExtensions.winter):
            return False

        # Skills are always directories containing SKILL.md.
        skill_links = self._symlink_entries(
            source_root=skills_root,
            target_root=self._config.workspace_root / ".claude" / "skills",
            prefix=manifest.prefix,
            kind="skill",
            repo_name=repo.name,
            reporter=reporter,
            include_dirs=True,
            include_files=False,
        )
        if skill_links is None:
            return False

        # Agents can be flat .md files or directories (nested-agents convention).
        agent_links = self._symlink_entries(
            source_root=agents_root,
            target_root=self._config.workspace_root / ".claude" / "agents",
            prefix=manifest.prefix,
            kind="agent",
            repo_name=repo.name,
            reporter=reporter,
            include_dirs=True,
            include_files=True,
            file_suffix=".md",
        )
        if agent_links is None:
            return False

        if skill_links or agent_links:
            detail = f"prefix={manifest.prefix} skills={len(skill_links)} agents={len(agent_links)}"
            reporter.repo_action(repo.name, str(repo.path), "extension_installed", detail)

        return True

    # ── Worktree lifecycle hooks ──────────────────────────────────────────

    def run_worktree_init_hooks(
        self,
        repos: list[StandaloneRepository],
        worktree_root: Path,
        worktree_name: str,
        reporter: IInitReporter,
    ) -> bool:
        """Run each installed extension's `on_worktree_init` hook.

        Called from `winter ws init <name>` after every project repo has been
        worktreed and its `cmd` list has run. The hook executes from the new
        worktree's directory so it can drop files in place, with env vars
        identifying the workspace, the extension, and the worktree.
        """
        if self._config.adopt_extensions == AdoptExtensions.none:
            return True

        success = True
        for repo in repos:
            if not repo.path.exists():
                continue
            manifest_path = repo.path / EXT_MANIFEST
            if not manifest_path.is_file():
                continue
            manifest = self._load_manifest(repo, manifest_path, reporter)
            if manifest is None:
                success = False
                continue
            hook = manifest.hooks.get(HOOK_ON_WORKTREE_INIT)
            if not hook:
                continue
            if not self._run_hook(repo, manifest, hook, worktree_root, worktree_name, reporter):
                success = False
        return success

    def _run_hook(
        self,
        repo: StandaloneRepository,
        manifest: ExtensionManifest,
        hook: str,
        worktree_root: Path,
        worktree_name: str,
        reporter: IInitReporter,
    ) -> bool:
        script_path = (repo.path / hook).resolve()
        try:
            script_path.relative_to(repo.path.resolve())
        except ValueError:
            reporter.repo_error(
                repo.name,
                f"hook path `{hook}` escapes the extension directory; refusing to run",
            )
            return False
        if not script_path.is_file():
            reporter.repo_error(repo.name, f"hook `{hook}` not found at {script_path}")
            return False
        if not os.access(script_path, os.X_OK):
            reporter.repo_error(repo.name, f"hook `{hook}` is not executable")
            return False

        index = resolve_worktree_index(worktree_name)
        env = os.environ.copy()
        env.update({
            "WINTER_WORKSPACE_DIR": str(self._config.workspace_root),
            "WINTER_EXT_DIR": str(repo.path),
            "WINTER_EXT_PREFIX": manifest.prefix,
            "WINTER_WORKTREE": worktree_name,
            "WINTER_WORKTREE_INDEX": str(index),
            "WINTER_PORT_BASE": str(PORT_BASE + index * PORT_STEP),
        })

        reporter.cmd_started(repo.name, f"hook on_worktree_init")
        try:
            proc = subprocess.Popen(
                [str(script_path)],
                cwd=str(worktree_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            reporter.repo_error(repo.name, f"hook on_worktree_init — {exc}")
            return False
        assert proc.stdout is not None
        for line in proc.stdout:
            reporter.cmd_output_line(repo.name, line.rstrip("\n"))
        returncode = proc.wait()
        reporter.cmd_completed(repo.name, "hook on_worktree_init", returncode)
        if returncode != 0:
            reporter.repo_error(
                repo.name,
                f"hook on_worktree_init exited with code {returncode}",
            )
            return False
        reporter.repo_action(
            repo.name, str(worktree_root), "hook_ran", "on_worktree_init"
        )
        return True

    # ── Manifest ──────────────────────────────────────────────────────────

    def _load_manifest(
        self,
        repo: StandaloneRepository,
        manifest_path: Path | None,
        reporter: IInitReporter,
    ) -> ExtensionManifest | None:
        data: dict = {}
        if manifest_path is not None:
            try:
                with manifest_path.open("rb") as f:
                    data = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                reporter.repo_error(repo.name, f"reading {EXT_MANIFEST} — {exc}")
                return None

        # Prefix resolution: workspace override > manifest prefix > manifest name > repo dir name.
        prefix = repo.prefix or data.get("prefix") or data.get("name") or repo.name

        # Manifest can declare an explicit dir; otherwise fall back to the
        # default search list which covers both winter and Claude Code conventions.
        skills_dirs = (data["skills_dir"],) if "skills_dir" in data else DEFAULT_SKILLS_DIRS
        agents_dirs = (data["agents_dir"],) if "agents_dir" in data else DEFAULT_AGENTS_DIRS

        hooks_raw = data.get("hooks") or {}
        hooks = {k: str(v) for k, v in hooks_raw.items() if isinstance(v, str)}

        return ExtensionManifest(
            prefix=prefix,
            skills_dirs=skills_dirs,
            agents_dirs=agents_dirs,
            hooks=hooks,
        )

    # ── Frontmatter validation ────────────────────────────────────────────

    def _validate_frontmatter(
        self,
        repo: StandaloneRepository,
        skills_root: Path | None,
        reporter: IInitReporter,
        strict: bool,
    ) -> bool:
        """Ensure SKILL.md files don't override the symlinked directory name.

        Claude Code lets the `name` frontmatter field override the directory name
        when discovering skills — that defeats the prefix-by-symlink design. In
        strict (`winter`) mode, refuse to install if any SKILL.md sets `name`.
        In `all` mode, the user opts into a less-curated experience, so we only warn.
        """
        if skills_root is None or not skills_root.is_dir():
            return True

        offenders: list[str] = []
        for entry in sorted(skills_root.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            name_field = self._extract_frontmatter_name(skill_md)
            if name_field is None:
                continue
            offenders.append(f"{entry.name}/SKILL.md sets `name: {name_field}`")

        if not offenders:
            return True

        msg = (
            f"extension {repo.name} has SKILL.md files with frontmatter `name` set, "
            f"which would override the prefixed directory name and break namespacing. "
            f"Remove the `name` field so the directory name (set by winter) is authoritative. "
            f"Offenders: {'; '.join(offenders)}"
        )
        if strict:
            reporter.repo_error(repo.name, msg)
            return False
        # adopt_extensions = "all": warn via repo_action so the user sees it but install proceeds.
        reporter.repo_action(repo.name, str(repo.path), "extension_warning", msg)
        return True

    @staticmethod
    def _extract_frontmatter_name(skill_md: Path) -> str | None:
        """Return the `name` field from YAML frontmatter, or None if not set.

        Looks only at the top-level frontmatter delimited by `---`. Returns None
        if there's no frontmatter, no `name` key, or any read error.
        """
        try:
            text = skill_md.read_text()
        except OSError:
            return None
        if not text.startswith("---"):
            return None
        # Find closing delimiter.
        lines = text.split("\n")
        if len(lines) < 2:
            return None
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx is None:
            return None
        for line in lines[1:end_idx]:
            stripped = line.strip()
            if stripped.startswith("name:"):
                value = stripped.split(":", 1)[1].strip()
                # Strip optional surrounding quotes.
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if value:
                    return value
        return None

    # ── Symlinks ──────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_existing_dir(base: Path, candidates: tuple[str, ...]) -> Path | None:
        """Return the first candidate path under `base` that exists as a directory."""
        for candidate in candidates:
            path = base / candidate
            if path.is_dir():
                return path
        return None

    def _symlink_entries(
        self,
        source_root: Path | None,
        target_root: Path,
        prefix: str,
        kind: str,
        repo_name: str,
        reporter: IInitReporter,
        include_dirs: bool,
        include_files: bool,
        file_suffix: str = "",
    ) -> list[str] | None:
        """Create one symlink per matching entry in `source_root`.

        For directory entries the symlink keeps the directory name (`<prefix>-<dirname>`).
        For file entries with a matching suffix the symlink keeps the full filename
        (`<prefix>-<filename>`), so a `.md` extension is preserved.

        Returns the list of created/existing symlink names on success, or None on error.
        Returns an empty list if `source_root` is None or doesn't exist.
        """
        if source_root is None or not source_root.is_dir():
            return []

        target_root.mkdir(parents=True, exist_ok=True)

        linked: list[str] = []
        for entry in sorted(source_root.iterdir()):
            if entry.is_dir():
                if not include_dirs:
                    continue
                link_name = f"{prefix}-{entry.name}"
            elif entry.is_file():
                if not include_files:
                    continue
                if file_suffix and not entry.name.endswith(file_suffix):
                    continue
                link_name = f"{prefix}-{entry.name}"
            else:
                continue

            link_path = target_root / link_name
            relative_target = self._relative_symlink_target(target_root, entry)

            if link_path.is_symlink():
                # Update if pointing at the wrong place.
                try:
                    current = link_path.readlink()
                except OSError:
                    current = None
                if current != relative_target:
                    try:
                        link_path.unlink()
                        link_path.symlink_to(relative_target)
                    except OSError as exc:
                        reporter.repo_error(repo_name, f"refresh {kind} symlink {link_name}: {exc}")
                        return None
                linked.append(link_name)
                continue

            if link_path.exists():
                reporter.repo_error(
                    repo_name,
                    f"cannot create {kind} symlink {link_name}: path exists and is not a symlink",
                )
                return None

            try:
                link_path.symlink_to(relative_target)
            except OSError as exc:
                reporter.repo_error(repo_name, f"create {kind} symlink {link_name}: {exc}")
                return None
            linked.append(link_name)

        return linked

    @staticmethod
    def _relative_symlink_target(link_dir: Path, target: Path) -> Path:
        """Compute the symlink target as a path relative to the link's parent directory.

        Relative targets keep the workspace portable — moving the workspace doesn't
        invalidate the links.
        """
        return Path(os.path.relpath(target, link_dir))

    # ── Workspace exclude management ──────────────────────────────────────

    def finalize_excludes(
        self,
        repos: list[StandaloneRepository],
        reporter: IInitReporter,
    ) -> bool:
        """Aggregate-update the workspace `.git/info/exclude` with one block per extension.

        Called once after all standalones are reconciled. Each block is bracketed
        with `# >>> <name> (managed by winter)` markers and lists the extension
        repo path plus the symlink globs under `.claude/skills/` and `.claude/agents/`.
        Orphan blocks for extensions no longer present are stripped automatically;
        if no extensions are eligible, every winter-managed block is removed.
        """
        if self._config.adopt_extensions == AdoptExtensions.none:
            return True

        exclude_path = self._config.workspace_root / ".git" / "info" / "exclude"

        existing = ""
        if exclude_path.exists():
            try:
                existing = exclude_path.read_text()
            except OSError as exc:
                reporter.repo_error(
                    CLAUDEMD_BLOCK_NAME,
                    f"reading .git/info/exclude — {exc}",
                )
                return False

        eligible: list[tuple[str, list[str]]] = []
        for repo in repos:
            resolved = self._resolve_for_excludes(repo)
            if resolved is None:
                continue
            relative, prefix = resolved
            begin = GITIGNORE_BEGIN.format(name=repo.name)
            end = GITIGNORE_END.format(name=repo.name)
            lines = [begin, f"/{relative}/"]
            if prefix is not None:
                lines.extend([
                    f".claude/skills/{prefix}-*",
                    f".claude/agents/{prefix}-*",
                ])
            lines.append(end)
            eligible.append((repo.name, lines))

        eligible_names = {name for name, _ in eligible}
        new_content = self._strip_orphan_managed_blocks(existing, eligible_names)
        for block_name, desired_lines in eligible:
            begin = GITIGNORE_BEGIN.format(name=block_name)
            end = GITIGNORE_END.format(name=block_name)
            new_content = replace_or_append_block(new_content, begin, end, desired_lines)

        if new_content == existing:
            return True

        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            exclude_path.write_text(new_content)
        except OSError as exc:
            reporter.repo_error(
                CLAUDEMD_BLOCK_NAME,
                f"writing .git/info/exclude — {exc}",
            )
            return False

        detail = ", ".join(sorted(eligible_names)) if eligible_names else "cleared"
        reporter.repo_action(
            CLAUDEMD_BLOCK_NAME,
            str(exclude_path),
            "workspace_excludes_updated",
            detail,
        )
        return True

    def _resolve_for_excludes(
        self,
        repo: StandaloneRepository,
    ) -> tuple[str, str | None] | None:
        """Resolve (relative_path, prefix) for an extension's exclude block, or None if not eligible.

        Every standalone repo cloned at a path under the workspace root gets its
        directory added to `.git/info/exclude` so it doesn't appear as untracked
        in the workspace repo — this applies regardless of manifest presence or
        adopt_extensions mode.

        `prefix` is only returned when the repo actually contributes symlinks
        under `.claude/skills/` or `.claude/agents/` (i.e. is being processed as
        an extension). When `prefix` is None, no symlink-glob lines are added
        to the exclude block.
        """
        if not repo.path.exists():
            return None
        try:
            relative = repo.path.relative_to(self._config.workspace_root).as_posix()
        except ValueError:
            return None
        mode = self._config.adopt_extensions
        manifest_path = repo.path / EXT_MANIFEST
        manifest_present = manifest_path.is_file()
        extension_eligible = (
            mode != AdoptExtensions.none
            and (manifest_present or mode == AdoptExtensions.all)
        )
        if not extension_eligible:
            return relative, None
        data: dict = {}
        if manifest_present:
            try:
                with manifest_path.open("rb") as f:
                    data = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                data = {}
        prefix = repo.prefix or data.get("prefix") or data.get("name") or repo.name
        return relative, prefix

    @staticmethod
    def _strip_orphan_managed_blocks(content: str, eligible_names: set[str]) -> str:
        """Remove any `# >>> X (managed by winter)` block whose X is not in `eligible_names`.

        The regex deliberately rejects names containing `/` so that namespaced
        blocks owned by other subsystems (e.g. `winter-dir/projects` written by
        InitService) are not treated as orphans of the extension flow.
        """
        pattern = re.compile(r"^# >>> ([^/]+?) \(managed by winter\)$")
        orphan_names: set[str] = set()
        for line in (content.split("\n") if content else []):
            m = pattern.match(line)
            if m:
                name = m.group(1)
                if name not in eligible_names:
                    orphan_names.add(name)
        result = content
        for name in orphan_names:
            begin = GITIGNORE_BEGIN.format(name=name)
            end = GITIGNORE_END.format(name=name)
            result = strip_block(result, begin, end)
        return result

    # ── CLAUDE.md "Winter Extensions" block ──────────────────────────────

    def finalize_claudemd(
        self,
        repos: list[StandaloneRepository],
        reporter: IInitReporter,
    ) -> bool:
        """Aggregate-update `CLAUDE.winter.md` with the extension list.

        Called once after all standalones are reconciled. Lists every
        standalone that has an `index.md` at its repo root, with a path
        description and an `@`-import line.

        The workspace's `CLAUDE.md` is expected to commit a stable
        `# Winter Extensions` section that imports `@CLAUDE.winter.md`; this
        CLI never touches `CLAUDE.md`. `CLAUDE.winter.md` is gitignored, so
        adding or removing extensions does not dirty the workspace.

        When no extensions are eligible, `CLAUDE.winter.md` is deleted.
        """
        if self._config.adopt_extensions == AdoptExtensions.none:
            return True

        eligible: list[tuple[str, str]] = []
        for repo in repos:
            index_path = repo.path / CLAUDEMD_INDEX_FILENAME
            if not index_path.is_file():
                continue
            try:
                relative = repo.path.relative_to(self._config.workspace_root).as_posix()
            except ValueError:
                # Standalone path lives outside the workspace; can't write a
                # workspace-relative @-import for it. Skip silently.
                continue
            eligible.append((repo.name, relative))

        winter_path = self._config.workspace_root / CLAUDEMD_WINTER_FILENAME

        if not eligible:
            if not winter_path.exists():
                return True
            try:
                winter_path.unlink()
            except OSError as exc:
                reporter.repo_error(
                    CLAUDEMD_BLOCK_NAME, f"removing {CLAUDEMD_WINTER_FILENAME} — {exc}"
                )
                return False
            reporter.repo_action(
                CLAUDEMD_BLOCK_NAME,
                str(winter_path),
                "claude_winter_removed",
                "no eligible extensions",
            )
            return True

        winter_lines = [
            f"- **{name}** at `./{rel}/` — resolves the `{name}:` path notation. @{rel}/{CLAUDEMD_INDEX_FILENAME}"
            for name, rel in sorted(eligible)
        ]
        new_winter = "\n".join(winter_lines) + "\n"

        existing_winter = ""
        if winter_path.exists():
            try:
                existing_winter = winter_path.read_text()
            except OSError as exc:
                reporter.repo_error(
                    CLAUDEMD_BLOCK_NAME, f"reading {CLAUDEMD_WINTER_FILENAME} — {exc}"
                )
                return False

        if new_winter == existing_winter:
            return True

        try:
            winter_path.write_text(new_winter)
        except OSError as exc:
            reporter.repo_error(
                CLAUDEMD_BLOCK_NAME, f"writing {CLAUDEMD_WINTER_FILENAME} — {exc}"
            )
            return False

        detail = ", ".join(name for name, _ in sorted(eligible))
        reporter.repo_action(
            CLAUDEMD_BLOCK_NAME,
            str(winter_path),
            "claude_winter_updated",
            detail,
        )
        return True
