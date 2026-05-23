from __future__ import annotations

import dataclasses
from typing import Any

from winter_cli.modules.workspace.models import ProjectRepository, Workspace
from winter_cli.modules.workspace.repository_factory import RepositoryFactory


@dataclasses.dataclass
class DriftReport:
    """Difference between the config-declared repo list and what's on disk."""

    missing: list[ProjectRepository]
    """Repos declared in config but absent from projects/."""

    undeclared: list[str]
    """Directories under projects/ that are not declared in config."""

    @property
    def any(self) -> bool:
        return bool(self.missing or self.undeclared)


class DriftWarningService:
    """Detects, formats, and emits drift warnings between `.winter/config.toml` and the `projects/` directory.

    Called by handlers that iterate repos (status/sync/connect/push/diff/list).
    Operations that don't touch repos skip the drift check entirely. The `click` module
    is injected so handlers don't have to wire echo themselves and tests can capture output.
    """

    def __init__(
        self,
        workspace: Workspace,
        repo_factory: RepositoryFactory,
        click: Any,
    ) -> None:
        self._workspace = workspace
        self._repo_factory = repo_factory
        self._click = click

    def detect(self) -> DriftReport:
        """Compare the config's project repo list against what exists under projects/.

        Missing repos are returned as their full domain model so callers can render
        display names, links, or other fields. Undeclared directories are returned
        as the literal names on disk.
        """
        project_repos = self._repo_factory.get_project_repos()
        projects_dir = self._workspace.root_path / "projects"

        on_disk: set[str] = set()
        if projects_dir.is_dir():
            on_disk = {p.name for p in projects_dir.iterdir() if p.is_dir() and not p.name.startswith(".")}

        declared = {r.name for r in project_repos}
        missing = sorted(
            (r for r in project_repos if r.name not in on_disk),
            key=lambda r: r.name,
        )
        undeclared = sorted(on_disk - declared)

        return DriftReport(missing=missing, undeclared=undeclared)

    def format_warning(self, report: DriftReport) -> str | None:
        """Human-readable single-line warning, or None when there's no drift."""
        if not report.any:
            return None
        parts = []
        if report.missing:
            names = ", ".join(r.name for r in report.missing)
            parts.append(f"missing from projects/: {names}")
        if report.undeclared:
            parts.append(f"undeclared in config: {', '.join(report.undeclared)}")
        return "Config and projects/ have drifted — " + "; ".join(parts)

    def raise_warning(self) -> None:
        """Detect drift, format the warning, and echo it to stderr if there is any."""
        report = self.detect()
        message = self.format_warning(report)
        if message:
            self._click.echo(f"warning: {message}", err=True)
