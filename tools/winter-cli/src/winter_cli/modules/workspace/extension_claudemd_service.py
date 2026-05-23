from __future__ import annotations

from winter_cli.config.models import AdoptExtensions, WorkspaceConfig
from winter_cli.core.filesystem import IFilesystemWriter
from winter_cli.modules.workspace.extension_manifest import (
    CLAUDEMD_BLOCK_NAME,
    CLAUDEMD_INDEX_FILENAME,
    CLAUDEMD_WINTER_FILENAME,
)
from winter_cli.modules.workspace.init_reporter import IInitReporter
from winter_cli.modules.workspace.models import StandaloneRepository


class ExtensionClaudemdService:
    """Aggregate-updates `CLAUDE.winter.md` with the list of installed extensions.

    The workspace's `CLAUDE.md` is expected to commit a stable
    `# Winter Extensions` section that imports `@CLAUDE.winter.md`; this CLI
    never touches `CLAUDE.md`. `CLAUDE.winter.md` is gitignored, so adding
    or removing extensions does not dirty the workspace.
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        fs: IFilesystemWriter,
    ) -> None:
        self._config = config
        self._fs = fs

    def finalize_claudemd(
        self,
        repos: list[StandaloneRepository],
        reporter: IInitReporter,
    ) -> bool:
        """Aggregate-update `CLAUDE.winter.md` with the extension list.

        Called once after all standalones are reconciled. Lists every
        standalone that has an `index.md` at its repo root, with a path
        description and an `@`-import line.

        When no extensions are eligible, `CLAUDE.winter.md` is deleted.
        """
        if self._config.adopt_extensions == AdoptExtensions.none:
            return True

        eligible: list[tuple[str, str]] = []
        for repo in repos:
            index_path = repo.path / CLAUDEMD_INDEX_FILENAME
            if not self._fs.is_file(index_path):
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
            if not self._fs.exists(winter_path):
                return True
            try:
                self._fs.unlink(winter_path)
            except OSError as exc:
                reporter.repo_error(CLAUDEMD_BLOCK_NAME, f"{CLAUDEMD_WINTER_FILENAME} — {exc}")
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

        try:
            existing_winter = self._fs.read_text(winter_path) if self._fs.exists(winter_path) else ""
            if new_winter == existing_winter:
                return True
            self._fs.write_text(winter_path, new_winter)
        except OSError as exc:
            reporter.repo_error(CLAUDEMD_BLOCK_NAME, f"{CLAUDEMD_WINTER_FILENAME} — {exc}")
            return False

        detail = ", ".join(name for name, _ in sorted(eligible))
        reporter.repo_action(
            CLAUDEMD_BLOCK_NAME,
            str(winter_path),
            "claude_winter_updated",
            detail,
        )
        return True
