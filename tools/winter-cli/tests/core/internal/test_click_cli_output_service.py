from __future__ import annotations

from winter_cli.core.cli_output_service import Cell
from winter_cli.core.internal.click_cli_output_service import ClickCliOutputService


def _strip_ansi(s: str) -> str:
    """Drop ANSI escape sequences so layout assertions stay style-agnostic."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def test_style_wraps_text_with_ansi_when_non_empty() -> None:
    svc = ClickCliOutputService()
    styled = svc.style("hello", "red")
    assert "hello" in styled
    assert "\x1b[" in styled  # ANSI escape present


def test_style_returns_empty_string_unchanged() -> None:
    svc = ClickCliOutputService()
    assert svc.style("", "red") == ""


def test_render_table_aligns_columns_with_gap() -> None:
    svc = ClickCliOutputService()
    lines = svc.render_table([["a", "bb"], ["ccc", "d"]], gap=2)
    assert [_strip_ansi(line) for line in lines] == ["a    bb", "ccc  d"]


def test_render_table_includes_header_row() -> None:
    svc = ClickCliOutputService()
    lines = svc.render_table([["alpha", "1"]], headers=["NAME", "COUNT"])
    stripped = [_strip_ansi(line) for line in lines]
    assert stripped[0] == "NAME   COUNT"
    assert stripped[1] == "alpha  1"


def test_render_table_drops_trailing_empty_cells() -> None:
    """Trailing empty cells shouldn't leave trailing whitespace on a row."""
    svc = ClickCliOutputService()
    lines = svc.render_table([["a", "b"], ["c", ""]])
    # Row 2's empty trailing cell collapses; only "c" remains (no trailing spaces).
    assert _strip_ansi(lines[1]) == "c"


def test_render_table_applies_row_style() -> None:
    svc = ClickCliOutputService()
    lines = svc.render_table([["x"]], row_styles=["dim"])
    assert "\x1b[" in lines[0]
    assert "x" in _strip_ansi(lines[0])


def test_render_table_handles_composed_cells() -> None:
    """A Cell.compose with multiple segments lays out by total plain length."""
    svc = ClickCliOutputService()
    cell = Cell.compose([("ok", "green"), (":", None), ("done", "bold")])
    lines = svc.render_table([[cell, "next"]])
    # Total plain width of the first column is len("ok:done") == 7, so the
    # second column ("next") starts after that plus the default gap (2).
    assert _strip_ansi(lines[0]) == "ok:done  next"
