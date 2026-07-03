"""CLI-level tests for `winter service up`/`down` argument parsing and the
`start`/`stop` aliases.

Covers:
- `up`/`down` with no PATTERNS exits non-zero (Click's `required=True` on the
  `nargs=-1` PATTERNS argument) — the explicit-target rule mirrors `restart`/`logs`.
- `up`/`down` still appear in `winter service --help`.
- `start`/`stop` are the exact same `click.Command` objects as `up`/`down`
  (object identity, not copy-pasted command bodies).
- `start`/`stop` forward options (`--wait`/`--timeout`/PATTERNS) identically to
  `up`/`down`, and always dispatch the `up`/`down` action word — never `start`/
  `stop` — onto `ServiceParams`, which is what `ServiceDispatchService.dispatch`
  forwards verbatim as the orchestrator's argv action token.
- `start`/`stop` are listed in `winter service --help`, annotated as aliases.

These assert purely on Click's argument-parsing behavior and on the
`ServiceParams` handed to a stubbed handler; no container/workspace wiring is
needed.
"""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from winter_cli.modules.service import command as command_module
from winter_cli.modules.service.command import down_cmd, service_group, up_cmd
from winter_cli.modules.service.handler import ServiceParams


def test_up_with_no_patterns_exits_nonzero() -> None:
    result = CliRunner().invoke(service_group, ["up"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_down_with_no_patterns_exits_nonzero() -> None:
    result = CliRunner().invoke(service_group, ["down"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_start_with_no_patterns_exits_nonzero() -> None:
    result = CliRunner().invoke(service_group, ["start"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_stop_with_no_patterns_exits_nonzero() -> None:
    result = CliRunner().invoke(service_group, ["stop"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_service_help_lists_up_and_down() -> None:
    result = CliRunner().invoke(service_group, ["--help"])
    assert result.exit_code == 0
    assert "up" in result.output
    assert "down" in result.output


def test_service_help_lists_start_and_stop_as_aliases() -> None:
    result = CliRunner().invoke(service_group, ["--help"])
    assert result.exit_code == 0
    assert "Alias of `up`" in result.output
    assert "Alias of `down`" in result.output


def test_start_is_the_same_command_object_as_up() -> None:
    """`start` is genuine sugar: the very same click.Command as `up`, not a copy."""
    ctx = click.Context(service_group)
    assert service_group.get_command(ctx, "start") is up_cmd


def test_stop_is_the_same_command_object_as_down() -> None:
    """`stop` is genuine sugar: the very same click.Command as `down`, not a copy."""
    ctx = click.Context(service_group)
    assert service_group.get_command(ctx, "stop") is down_cmd


class _RecordingHandler:
    """Stub ServiceHandler that records the ServiceParams passed to `run`."""

    def __init__(self) -> None:
        self.calls: list[ServiceParams] = []

    def run(self, params: ServiceParams) -> None:
        self.calls.append(params)


def _invoke_capturing_params(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> ServiceParams:
    handler = _RecordingHandler()
    monkeypatch.setattr(command_module, "_service_handler", lambda ctx: handler)
    result = CliRunner().invoke(service_group, args)
    assert result.exit_code == 0, result.output
    assert len(handler.calls) == 1
    return handler.calls[0]


def test_start_dispatches_the_same_service_params_as_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """`start alpha --wait --timeout 5` produces the identical ServiceParams as `up`.

    In particular the dispatched `action` is the literal string `"up"` — never
    `"start"` — which is what `ServiceDispatchService.dispatch` forwards
    verbatim as the orchestrator's argv action token
    (`src/winter_cli/modules/service/service_dispatch_service.py`), so the
    orchestrator never sees `start` on the wire.
    """
    up_params = _invoke_capturing_params(monkeypatch, ["up", "alpha", "--wait", "--timeout", "5"])
    start_params = _invoke_capturing_params(monkeypatch, ["start", "alpha", "--wait", "--timeout", "5"])

    assert start_params == up_params
    assert start_params.action == "up"
    assert start_params.patterns == ("alpha",)
    assert start_params.wait is True
    assert start_params.timeout_s == 5.0


def test_stop_dispatches_the_same_service_params_as_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stop alpha beta/api` produces the identical ServiceParams as `down`.

    The dispatched `action` is the literal string `"down"` — never `"stop"`.
    """
    down_params = _invoke_capturing_params(monkeypatch, ["down", "alpha", "beta/api"])
    stop_params = _invoke_capturing_params(monkeypatch, ["stop", "alpha", "beta/api"])

    assert stop_params == down_params
    assert stop_params.action == "down"
    assert stop_params.patterns == ("alpha", "beta/api")
