from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Cell:
    """A table cell composed of styled segments.

    Use ``Cell.of(text, style=...)`` for a single-style cell, or
    ``Cell.compose([(text, style), ...])`` for a cell built from multiple
    independently-styled segments. The concatenated plain text is used for
    column-width computation so ANSI escapes never perturb alignment.
    """

    segments: tuple[tuple[str, str | None], ...]

    @classmethod
    def of(cls, text: str, style: str | None = None) -> "Cell":
        return cls(((text, style),))

    @classmethod
    def compose(cls, segments: Iterable[tuple[str, str | None]]) -> "Cell":
        return cls(tuple(segments))

    @property
    def text(self) -> str:
        return "".join(seg for seg, _ in self.segments)


class ICliOutputService(Protocol):
    """Protocol for CLI output rendering — handlers depend on this seam.

    Style names accepted by ``style()`` and Cell segments: standard color names
    (``red``, ``green``, ``yellow``, ``blue``, ``magenta``, ``cyan``), plus
    ``bold``, ``dim``, and ``dark_orange``. Implementations may map these to
    ANSI escapes, HTML, or any other rendering target.
    """

    def style(self, text: str, style: str) -> str: ...

    def render_table(
        self,
        rows: Iterable[Sequence[str | Cell]],
        *,
        headers: Sequence[str | Cell] | None = None,
        row_styles: Sequence[str | None] | None = None,
        gap: int = 2,
    ) -> list[str]: ...
