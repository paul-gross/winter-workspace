from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
REFRESH_INTERVAL = 30


class RefreshStatus(Static):
    refreshing: reactive[bool] = reactive(False)

    def __init__(self, interval: int = REFRESH_INTERVAL, **kwargs) -> None:
        super().__init__(**kwargs)
        self._interval = interval
        self._countdown = interval
        self._spinner_idx = 0

    def on_mount(self) -> None:
        self.set_interval(0.1, self._tick_spinner)
        self.set_interval(1, self._tick_countdown)

    def start_refresh(self) -> None:
        self.refreshing = True
        self._spinner_idx = 0

    def finish_refresh(self) -> None:
        self.refreshing = False
        self._countdown = self._interval

    def _tick_spinner(self) -> None:
        if not self.refreshing:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(SPINNER_FRAMES)
        self.update(self._render_status())

    def _tick_countdown(self) -> None:
        if self.refreshing:
            return
        self._countdown = max(0, self._countdown - 1)
        self.update(self._render_status())

    def _render_status(self) -> Text:
        if self.refreshing:
            frame = SPINNER_FRAMES[self._spinner_idx]
            return Text.assemble(
                (f"{frame} ", "cyan"),
                ("refreshing…", "dim"),
            )
        return Text(f"{self._countdown}s", style="dim")
