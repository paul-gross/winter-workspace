from __future__ import annotations

import json
from pathlib import Path

from winter_cli.modules.capability.capability_reporter import JsonCapabilityReporter, StreamCapabilityReporter
from winter_cli.modules.capability.models import CapabilityCandidate, CapabilitySlot, SlotResolution


class FakeClick:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def echo(self, message: str = "", err: bool = False) -> None:
        self.lines.append(message)

    def style(self, text: str, **kwargs: object) -> str:
        return text


_WS = Path("/ws")
_TMUX = _WS / "winter-service-tmux"
_DOCKER = _WS / "winter-service-docker"


def _candidate(
    name: str,
    ext_dir: Path,
    entrypoint_rel: str = "workflow/service",
    valid: bool = True,
) -> CapabilityCandidate:
    return CapabilityCandidate(
        extension_name=name,
        entrypoint_rel=entrypoint_rel,
        entrypoint_path=ext_dir / entrypoint_rel,
        ext_dir=ext_dir,
        prefix=name,
        entrypoint_valid=valid,
    )


def _tmux_candidate(valid: bool = True) -> CapabilityCandidate:
    return _candidate("winter-service-tmux", _TMUX, valid=valid)


def _docker_candidate(valid: bool = True) -> CapabilityCandidate:
    return _candidate("winter-service-docker", _DOCKER, valid=valid)


# ── Stream reporter ───────────────────────────────────────────────────────────


def test_stream_explicit_valid() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(valid=True),),
        bound_extension="winter-service-tmux",
        binding_kind="explicit",
        error=None,
    )
    StreamCapabilityReporter(click).render([resolution])
    assert len(click.lines) == 1
    line = click.lines[0]
    assert "service" in line
    assert "winter-service-tmux" in line
    assert "explicit" in line
    assert "✓" in line


def test_stream_implicit_valid() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(valid=True),),
        bound_extension=None,
        binding_kind="implicit",
        error=None,
    )
    StreamCapabilityReporter(click).render([resolution])
    assert len(click.lines) == 1
    line = click.lines[0]
    assert "service" in line
    assert "winter-service-tmux" in line
    assert "implicit" in line
    assert "✓" in line


def test_stream_ambiguous_lists_candidates() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(), _docker_candidate()),
        bound_extension=None,
        binding_kind="unbound",
        error=None,
    )
    StreamCapabilityReporter(click).render([resolution])
    # First line says unbound with 2 candidates
    assert "unbound" in click.lines[0]
    assert "2" in click.lines[0]
    assert "winter-service-tmux" in click.lines[0]
    assert "winter-service-docker" in click.lines[0]
    # Indented candidate lines
    assert len(click.lines) == 3
    assert click.lines[1].startswith("  -")
    assert click.lines[2].startswith("  -")


def test_stream_no_provider() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(),
        bound_extension=None,
        binding_kind="unbound",
        error=None,
    )
    StreamCapabilityReporter(click).render([resolution])
    assert len(click.lines) == 1
    assert "no provider" in click.lines[0]


def test_stream_invalid() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(),
        bound_extension="winter-service-tmux",
        binding_kind="invalid",
        error="capabilities.service provider 'winter-service-tmux' entrypoint not found at /ws/winter-service-tmux/workflow/service.",
    )
    StreamCapabilityReporter(click).render([resolution])
    assert len(click.lines) == 1
    line = click.lines[0]
    assert "invalid" in line
    assert "winter-service-tmux" in line
    assert "entrypoint not found" in line


def test_stream_explicit_invalid_entrypoint() -> None:
    """Explicit binding where candidate has invalid entrypoint shows ✗."""
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(valid=False),),
        bound_extension="winter-service-tmux",
        binding_kind="invalid",
        error="capabilities.service provider 'winter-service-tmux' entrypoint not found at /ws/winter-service-tmux/workflow/service.",
    )
    StreamCapabilityReporter(click).render([resolution])
    line = click.lines[0]
    assert "invalid" in line


# ── JSON reporter ─────────────────────────────────────────────────────────────


def test_json_explicit_valid() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(valid=True),),
        bound_extension="winter-service-tmux",
        binding_kind="explicit",
        error=None,
    )
    JsonCapabilityReporter(click).render([resolution])
    payload = json.loads(click.lines[0])
    assert len(payload) == 1
    obj = payload[0]
    assert obj["slot"] == "service"
    assert obj["bound"] == "winter-service-tmux"
    assert obj["binding_kind"] == "explicit"
    assert obj["ambiguous"] is False
    assert obj["error"] is None
    assert obj["candidates"] == [{"extension": "winter-service-tmux", "entrypoint": "workflow/service", "valid": True}]


def test_json_implicit() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(valid=True),),
        bound_extension=None,
        binding_kind="implicit",
        error=None,
    )
    JsonCapabilityReporter(click).render([resolution])
    payload = json.loads(click.lines[0])
    obj = payload[0]
    assert obj["bound"] is None
    assert obj["binding_kind"] == "implicit"
    assert obj["ambiguous"] is False


def test_json_ambiguous() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(), _docker_candidate()),
        bound_extension=None,
        binding_kind="unbound",
        error=None,
    )
    JsonCapabilityReporter(click).render([resolution])
    payload = json.loads(click.lines[0])
    obj = payload[0]
    assert obj["ambiguous"] is True
    assert obj["binding_kind"] == "unbound"
    assert len(obj["candidates"]) == 2


def test_json_no_provider() -> None:
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(),
        bound_extension=None,
        binding_kind="unbound",
        error=None,
    )
    JsonCapabilityReporter(click).render([resolution])
    payload = json.loads(click.lines[0])
    obj = payload[0]
    assert obj["ambiguous"] is False
    assert obj["candidates"] == []
    assert obj["bound"] is None


def test_json_invalid() -> None:
    click = FakeClick()
    err_msg = "capabilities.service = 'missing' — no installed extension named 'missing'"
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(),
        bound_extension="missing",
        binding_kind="invalid",
        error=err_msg,
    )
    JsonCapabilityReporter(click).render([resolution])
    payload = json.loads(click.lines[0])
    obj = payload[0]
    assert obj["binding_kind"] == "invalid"
    assert obj["error"] == err_msg
    assert obj["bound"] == "missing"


def test_json_emits_single_line() -> None:
    """JSON reporter emits exactly one echo call."""
    click = FakeClick()
    resolution = SlotResolution(
        slot=CapabilitySlot.service,
        candidates=(_tmux_candidate(),),
        bound_extension="winter-service-tmux",
        binding_kind="explicit",
        error=None,
    )
    JsonCapabilityReporter(click).render([resolution])
    assert len(click.lines) == 1
