from __future__ import annotations

from rich.text import Text

from winter_cli.modules.workspace.models import WorktreeRepoStatus


def render_repo_cell(repo_status: WorktreeRepoStatus, include_extensions: bool = True) -> Text:
    parts: list[tuple[str, str]] = []

    if repo_status.ahead > 0:
        parts.append((f"+{repo_status.ahead}", "green"))
    if repo_status.behind > 0:
        parts.append((f"-{repo_status.behind}", "yellow"))

    if repo_status.dirty_count == 1:
        parts.append(("1 file", "red"))
    elif repo_status.dirty_count > 1:
        parts.append((f"{repo_status.dirty_count} files", "red"))

    # The cyan `[+N, -N]` and orange `[+]` markers describe divergence
    # against the *tracking* branch — only meaningful when that ref differs
    # from the main branch (otherwise the green/yellow counts above already
    # say the same thing). Pinned repos always track main, so they're
    # filtered out automatically by this comparison.
    main_ref = (
        f"origin/{repo_status.worktree.repository.main_branch}" if repo_status.worktree.repository.main_branch else None
    )
    tracking_differs_from_main = repo_status.tracking_branch is not None and repo_status.tracking_branch != main_ref

    # `[+]` flags a non-pinned repo whose upstream is configured but the
    # remote-tracking ref doesn't exist locally yet — i.e., we're set up to
    # push to a feature branch that doesn't exist on origin, AND we actually
    # have commits the first push would carry across.
    unborn_upstream = tracking_differs_from_main and not repo_status.tracking_ref_present and repo_status.ahead > 0

    has_tracking_divergence = tracking_differs_from_main and (
        repo_status.tracking_ahead > 0 or repo_status.tracking_behind > 0
    )
    if len(parts) == 0 and not unborn_upstream and not has_tracking_divergence:
        return Text("·", style="dim")

    text = Text()
    for i, (label, style) in enumerate(parts):
        if i > 0:
            text.append(" ")
        text.append(label, style=style)

    if has_tracking_divergence:
        inner_parts = []
        if repo_status.tracking_ahead > 0:
            inner_parts.append(f"+{repo_status.tracking_ahead}")
        if repo_status.tracking_behind > 0:
            inner_parts.append(f"-{repo_status.tracking_behind}")
        prefix = " " if parts else ""
        text.append(f"{prefix}[{', '.join(inner_parts)}]", style="cyan")
    elif unborn_upstream:
        # Upstream configured but never fetched / never pushed. The bare
        # `[+]` (no count) reads as "ahead, by an unknown amount" alongside
        # the existing `[+N]` notation; orange flags it as a distinct state
        # — local config points somewhere that doesn't exist on the remote.
        prefix = " " if parts else ""
        text.append(f"{prefix}[+]", style="dark_orange")

    # The worktree-detail table carries extensions in a dedicated column, so it
    # asks for the bare status cell; the matrix inlines the badges here.
    if include_extensions:
        for key, value in repo_status.extensions.items():
            if key.startswith("_"):
                continue
            text.append(" ")
            if isinstance(value, Text):
                text.append(value)
            else:
                badge = str(value) if value else key
                text.append(badge, style="cyan")

    return text
