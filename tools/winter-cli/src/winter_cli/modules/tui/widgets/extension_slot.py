from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class ExtensionSlot(Widget):
    extensions: reactive[dict[str, dict]] = reactive({})

    def __init__(self, extensions: dict[str, dict] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if extensions is not None:
            self.extensions = extensions

    def compose(self):
        for key, value in self.extensions.items():
            label = str(value) if value else key
            yield Static(f" [{key}:{label}] ", classes="extension-badge")

    def watch_extensions(self) -> None:
        self.remove_children()
        for key, value in self.extensions.items():
            label = str(value) if value else key
            self.mount(Static(f" [{key}:{label}] ", classes="extension-badge"))
