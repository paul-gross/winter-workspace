"""Shared per-repo detail body: built-in git info plus plugin-contributed panels.

Both the feature-environment (`WorktreeDetailScreen`) and standalone
(`StandaloneDetailScreen`) detail views render the *same* single-repo body — a
`RepoStatus` summary (branch / tracking / dirty files / recent commits) and any
`IDetailPanel`s a plugin contributed. This widget is that body.

With zero contributed panels it renders exactly the built-in info `Static` (no
tab bar). With one or more panels it renders a `TabbedContent` whose first tab
is the built-in info and whose remaining tabs are the panels — so a screen never
shows an empty tab bar.

Panel rendering is pure (no widget access) so it runs in the screens' refresh
worker thread; `render_detail_panels` isolates each panel — a panel that raises
yields an error `PanelOutcome` rather than taking down the screen, matching the
decorator error handling.
"""

from __future__ import annotations

import dataclasses
from typing import cast

from rich.console import RenderableType
from rich.protocol import is_renderable
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane

from winter_cli.modules.workspace.models import RepoStatus
from winter_cli.plugins.types import DetailPanelContext, IDetailPanel


@dataclasses.dataclass
class PanelOutcome:
    """Result of rendering one `IDetailPanel` — either content or an error message.

    Aligned by index with the panel list. `error` is set (and `content` is a
    fallback marker) when the panel's `render` raised, so the screen can show an
    isolated error state for that one tab.
    """

    content: RenderableType
    error: str | None = None


def render_detail_panels(panels: list[IDetailPanel], context: DetailPanelContext) -> list[PanelOutcome]:
    """Render every panel against `context`, isolating failures per panel.

    Pure and widget-free so it can run off the UI thread. A panel that raises is
    caught here and reported as an error `PanelOutcome`; a panel that returns a
    non-renderable value is coerced to its `str()` so `Static.update` can't fail
    later in the compositor.
    """
    outcomes: list[PanelOutcome] = []
    for panel in panels:
        try:
            rendered = panel.render(context)
        except Exception as exc:
            # A buggy panel must not crash the screen — isolate it as an error
            # outcome, mirroring the loader's load-and-skip-on-error contract.
            outcomes.append(PanelOutcome(content=f"[red]Panel error:[/red] {exc}", error=str(exc)))
            continue
        content = cast(RenderableType, rendered) if is_renderable(rendered) else str(rendered)
        outcomes.append(PanelOutcome(content=content))
    return outcomes


def _upstream_line(detail: RepoStatus) -> str:
    """One line that makes the upstream's state unambiguous.

    Three distinct states the old flat `Tracking: <branch>` conflated:
    no upstream at all, an upstream whose remote ref doesn't resolve yet
    (configured but never pushed/fetched — `tracking_ref_present == False`),
    and a tracked-and-present upstream with its ahead/behind divergence.
    """
    tracking = detail.tracking_branch
    if tracking is None:
        return "Upstream: [dim]none[/dim]"
    if not detail.tracking_ref_present:
        return f"Upstream: [dark_orange]{tracking} configured, not yet pushed/fetched[/dark_orange]"
    return f"Upstream: tracking {tracking} — ahead {detail.tracking_ahead}, behind {detail.tracking_behind}"


def build_repo_info_markup(detail: RepoStatus) -> str:
    """Build the built-in info panel's console markup from a repo's status.

    Branch / upstream / main-divergence header plus the dirty-file list. The
    commit history is rendered separately by `build_commit_graph` into its own
    scrollable area.
    """
    lines = [
        f"[bold]{detail.name}[/bold]",
        f"Branch:   {detail.branch or '—'}",
        _upstream_line(detail),
    ]
    if detail.main_branch:
        lines.append(f"[dim]vs origin/{detail.main_branch}:[/dim] ahead {detail.ahead}, behind {detail.behind}")

    if len(detail.dirty_files) > 0:
        lines.append(f"\n[bold]Modified ({len(detail.dirty_files)}):[/bold]")
        for f in detail.dirty_files[:15]:
            lines.append(f"  {f}")
        remaining = len(detail.dirty_files) - 15
        if remaining > 0:
            lines.append(f"  ... and {remaining} more")

    return "\n".join(lines)


def build_commit_graph(detail: RepoStatus) -> Text:
    """Render the `git log --graph` history as a Rich `Text` for the scroll area.

    Built by appending plain lines (never markup parsing) so graph glyphs and
    commit subjects can't be mis-read as console markup. Abbreviated hashes are
    highlighted so the topology reads like `git log`.
    """
    if not detail.commit_graph:
        if detail.main_branch:
            return Text(f"No commits beyond origin/{detail.main_branch}.", style="dim")
        return Text("No commit history.", style="dim")

    text = Text()
    for i, line in enumerate(detail.commit_graph):
        if i > 0:
            text.append("\n")
        text.append(line)
    # The leading hex token on a `--oneline` row is the abbreviated hash; tint it
    # so commits stand out from the graph glyphs and decorations.
    text.highlight_regex(r"\b[0-9a-f]{7,40}\b", "yellow")
    return text


class RepoDetailView(Vertical):
    """The single-repo detail body — built-in info plus contributed panel tabs.

    Construct with the plugin registry's `detail_panels`. The tab structure is
    fixed at compose time because the registered panels are static for the life
    of a dashboard session.
    """

    def __init__(self, panels: list[IDetailPanel], **kwargs) -> None:
        super().__init__(**kwargs)
        self._panels = panels

    def compose(self):
        if not self._panels:
            yield from self._compose_info_body()
            return
        with TabbedContent(id="detail-tabs"):
            with TabPane("Info", id="detail-tab-info"):
                yield from self._compose_info_body()
            for i, panel in enumerate(self._panels):
                with TabPane(panel.title, id=f"detail-tab-{i}"):
                    yield Static(id=f"detail-panel-{i}")

    def _compose_info_body(self):
        """The built-in Info body: a fixed status header above a scrollable graph.

        Shared by the bare (no-panels) layout and the "Info" tab so the commit
        history scrolls in both — `#repo-info` sizes to its content while the
        graph fills and scrolls the remaining height.
        """
        yield Static(id="repo-info")
        with VerticalScroll(id="repo-graph-scroll"):
            yield Static(id="repo-graph")

    def show_repo(self, detail: RepoStatus, outcomes: list[PanelOutcome]) -> None:
        """Update the built-in info and every contributed panel from a fresh refresh.

        `outcomes` is aligned by index with the panels this view composed, so it
        maps one-to-one onto the `#detail-panel-{i}` statics.
        """
        self.query_one("#repo-info", Static).update(build_repo_info_markup(detail))
        self.query_one("#repo-graph", Static).update(build_commit_graph(detail))
        for i, outcome in enumerate(outcomes[: len(self._panels)]):
            self.query_one(f"#detail-panel-{i}", Static).update(outcome.content)
