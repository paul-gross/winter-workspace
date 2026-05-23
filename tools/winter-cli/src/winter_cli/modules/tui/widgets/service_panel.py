from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from winter_cli.modules.workspace.models import FeatureEnvironmentStatus


class ServicePanel(Static):
    statuses: reactive[list[FeatureEnvironmentStatus]] = reactive(list, always_update=True)

    def render(self) -> Text:
        if len(self.statuses) == 0:
            return Text("No worktrees", style="dim")

        text = Text()
        text.append("Services  ", style="bold")

        for i, env_status in enumerate(self.statuses):
            if i > 0:
                text.append("  ")

            badges = " ".join(v for v in env_status.extensions.values() if v)
            if badges:
                text.append(f"{badges} ")
            text.append(env_status.environment.name)

        return text
