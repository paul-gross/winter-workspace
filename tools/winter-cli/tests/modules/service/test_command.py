"""CLI-level tests for `winter service up`/`down` argument parsing.

Covers:
- `up`/`down` with no PATTERNS exits non-zero (Click's `required=True` on the
  `nargs=-1` PATTERNS argument) — the explicit-target rule mirrors `restart`/`logs`.
- `up`/`down` still appear in `winter service --help`.

These assert purely on Click's argument-parsing behavior, which runs before the
command callback is invoked — no container/workspace wiring is needed.
"""

from __future__ import annotations

from click.testing import CliRunner

from winter_cli.modules.service.command import service_group


def test_up_with_no_patterns_exits_nonzero() -> None:
    result = CliRunner().invoke(service_group, ["up"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_down_with_no_patterns_exits_nonzero() -> None:
    result = CliRunner().invoke(service_group, ["down"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_service_help_lists_up_and_down() -> None:
    result = CliRunner().invoke(service_group, ["--help"])
    assert result.exit_code == 0
    assert "up" in result.output
    assert "down" in result.output
