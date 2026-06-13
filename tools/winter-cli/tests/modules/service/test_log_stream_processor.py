from __future__ import annotations

from datetime import UTC, datetime

from winter_cli.modules.service.log_stream_processor import LogStreamProcessor
from winter_cli.modules.service.models import LogOptions


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def _opts(**kwargs: object) -> LogOptions:
    defaults: dict[str, object] = {
        "services": (),
        "follow": False,
        "tail": 200,
        "since_rfc3339": "",
        "until_rfc3339": "",
        "timestamps": False,
    }
    defaults.update(kwargs)
    return LogOptions(**defaults)  # type: ignore[arg-type]


def _process(
    options: LogOptions,
    lines: list[str],
    since_dt: datetime | None = None,
    until_dt: datetime | None = None,
) -> list[str]:
    """Run the processor over `lines` and return all rendered output."""
    proc = LogStreamProcessor(options, since_dt, until_dt)
    result = list(proc.process_lines(lines))
    result.extend(proc.finalize())
    return result


# ── basic rendering ───────────────────────────────────────────────────────────


def test_renders_plain_msg_with_svc_prefix_for_all_services() -> None:
    """Empty services (all) is multi-service scope — svc prefix is applied."""
    lines = ['{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"started"}']
    out = _process(_opts(services=()), lines)
    assert out == ["api | started"]


def test_multi_service_adds_svc_prefix() -> None:
    """When ≥2 explicit services requested, each line gets `<svc> | ` prefix."""
    lines = [
        '{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"up"}',
        '{"ts":"2026-06-13T10:00:02Z","svc":"db","msg":"ready"}',
    ]
    # Two explicit services → multi-service scope → prefix.
    out = _process(_opts(services=("api", "db")), lines)
    assert "api | up" in out
    assert "db | ready" in out


def test_single_explicit_service_no_prefix() -> None:
    """Single explicit service → no svc prefix, per the spec."""
    lines = ['{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"up"}']
    out = _process(_opts(services=("api",)), lines)
    assert out == ["up"]


# ── service filter ────────────────────────────────────────────────────────────


def test_service_filter_drops_non_matching_svc() -> None:
    lines = [
        '{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"api-msg"}',
        '{"ts":"2026-06-13T10:00:02Z","svc":"db","msg":"db-msg"}',
    ]
    out = _process(_opts(services=("api",)), lines)
    assert out == ["api-msg"]


def test_service_filter_multi_keeps_both() -> None:
    lines = [
        '{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"api-msg"}',
        '{"ts":"2026-06-13T10:00:02Z","svc":"db","msg":"db-msg"}',
        '{"ts":"2026-06-13T10:00:03Z","svc":"worker","msg":"worker-msg"}',
    ]
    out = _process(_opts(services=("api", "db")), lines)
    # Two explicit services → multi-service scope → svc prefixes in output.
    assert any("api-msg" in line for line in out)
    assert any("db-msg" in line for line in out)
    assert not any("worker-msg" in line for line in out)


def test_service_filter_empty_set_keeps_all() -> None:
    lines = [
        '{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"m1"}',
        '{"ts":"2026-06-13T10:00:02Z","svc":"db","msg":"m2"}',
    ]
    out = _process(_opts(services=()), lines)
    assert len(out) == 2


# ── since / until with ts ─────────────────────────────────────────────────────


def test_since_drops_lines_before_threshold() -> None:
    lines = [
        '{"ts":"2026-06-13T10:00:00Z","svc":"api","msg":"too-old"}',
        '{"ts":"2026-06-13T10:00:05Z","svc":"api","msg":"fresh"}',
    ]
    since = _dt("2026-06-13T10:00:03Z")
    out = _process(_opts(services=("api",)), lines, since_dt=since)
    assert out == ["fresh"]


def test_since_boundary_is_inclusive() -> None:
    """A line whose ts exactly equals the since threshold is kept (inclusive boundary)."""
    threshold = _dt("2026-06-13T10:00:03Z")
    lines = ['{"ts":"2026-06-13T10:00:03Z","svc":"api","msg":"at-boundary"}']
    out = _process(_opts(services=("api",)), lines, since_dt=threshold)
    assert out == ["at-boundary"]


def test_until_drops_lines_after_threshold() -> None:
    lines = [
        '{"ts":"2026-06-13T09:59:58Z","svc":"api","msg":"old"}',
        '{"ts":"2026-06-13T10:00:10Z","svc":"api","msg":"future"}',
    ]
    until = _dt("2026-06-13T10:00:00Z")
    out = _process(_opts(services=("api",)), lines, until_dt=until)
    assert out == ["old"]


def test_until_boundary_is_inclusive() -> None:
    """A line whose ts exactly equals the until threshold is kept (inclusive boundary)."""
    threshold = _dt("2026-06-13T10:00:00Z")
    lines = ['{"ts":"2026-06-13T10:00:00Z","svc":"api","msg":"at-boundary"}']
    out = _process(_opts(services=("api",)), lines, until_dt=threshold)
    assert out == ["at-boundary"]


def test_since_until_combined() -> None:
    lines = [
        '{"ts":"2026-06-13T09:00:00Z","svc":"api","msg":"before"}',
        '{"ts":"2026-06-13T10:00:00Z","svc":"api","msg":"in-window"}',
        '{"ts":"2026-06-13T11:00:00Z","svc":"api","msg":"after"}',
    ]
    since = _dt("2026-06-13T09:30:00Z")
    until = _dt("2026-06-13T10:30:00Z")
    out = _process(_opts(services=("api",)), lines, since_dt=since, until_dt=until)
    assert out == ["in-window"]


# ── since / until with lines that have no ts ─────────────────────────────────


def test_tsless_lines_kept_when_time_filter_active() -> None:
    lines = [
        '{"svc":"api","msg":"no-timestamp"}',
        '{"ts":"2026-06-13T10:00:00Z","svc":"api","msg":"in-window"}',
    ]
    since = _dt("2026-06-13T09:00:00Z")
    proc = LogStreamProcessor(_opts(services=("api",)), since, None)
    result = list(proc.process_lines(lines))
    result.extend(proc.finalize())
    # Both lines kept; tsless line cannot be time-filtered.
    assert "no-timestamp" in result
    assert "in-window" in result


def test_tsless_line_sets_time_filter_warning() -> None:
    lines = ['{"svc":"api","msg":"no-ts"}']
    since = _dt("2026-06-13T09:00:00Z")
    proc = LogStreamProcessor(_opts(services=("api",)), since, None)
    list(proc.process_lines(lines))
    assert proc.time_filter_warning is True


def test_no_tsless_no_warning() -> None:
    lines = ['{"ts":"2026-06-13T10:00:00Z","svc":"api","msg":"ok"}']
    since = _dt("2026-06-13T09:00:00Z")
    proc = LogStreamProcessor(_opts(services=("api",)), since, None)
    list(proc.process_lines(lines))
    assert proc.time_filter_warning is False


# ── tail ring-buffer (non-follow) ─────────────────────────────────────────────


def test_tail_limits_output_to_last_n_lines() -> None:
    lines = [f'{{"svc":"api","msg":"line-{i}"}}' for i in range(10)]
    out = _process(_opts(tail=3), lines)
    # Empty services = multi-service scope, so svc prefix is applied.
    assert len(out) == 3
    assert "line-7" in out[0]
    assert "line-8" in out[1]
    assert "line-9" in out[2]


def test_tail_all_returns_all_lines() -> None:
    lines = [f'{{"svc":"api","msg":"line-{i}"}}' for i in range(5)]
    out = _process(_opts(tail="all"), lines)
    assert len(out) == 5


def test_tail_zero_lines_returns_zero_in_non_follow() -> None:
    lines = [f'{{"svc":"api","msg":"line-{i}"}}' for i in range(5)]
    # tail=0 would be invalid via CLI (positive int required), but
    # processor handles deque(maxlen=0) gracefully — no output.
    # Use a single explicit service to avoid multi-service prefix complications.
    proc = LogStreamProcessor(_opts(tail=0, follow=False, services=("api",)), None, None)
    result = list(proc.process_lines(lines))
    result.extend(proc.finalize())
    assert result == []


# ── follow skips tail ─────────────────────────────────────────────────────────


def test_follow_mode_emits_lines_immediately_without_tail() -> None:
    """In follow mode the ring buffer is None and lines are yielded in process_lines."""
    lines = [f'{{"svc":"api","msg":"line-{i}"}}' for i in range(10)]
    proc = LogStreamProcessor(_opts(follow=True, tail=3, services=("api",)), None, None)
    from_process = list(proc.process_lines(lines))
    from_finalize = list(proc.finalize())
    # All 10 lines come out of process_lines; finalize is a no-op.
    assert len(from_process) == 10
    assert from_finalize == []


# ── timestamps rendering ──────────────────────────────────────────────────────


def test_timestamps_flag_prepends_ts() -> None:
    lines = ['{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"hi"}']
    out = _process(_opts(timestamps=True), lines)
    assert out[0].startswith("2026-06-13T10:00:01Z")
    assert "hi" in out[0]


def test_timestamps_with_tsless_line_sets_warning() -> None:
    lines = ['{"svc":"api","msg":"no-ts"}']
    proc = LogStreamProcessor(_opts(timestamps=True), None, None)
    result = list(proc.process_lines(lines))
    result.extend(proc.finalize())
    # Message still rendered even without ts prefix.
    assert "no-ts" in result[0]
    assert proc.timestamps_warning is True


def test_timestamps_flag_false_no_warning() -> None:
    lines = ['{"svc":"api","msg":"no-ts"}']
    proc = LogStreamProcessor(_opts(timestamps=False), None, None)
    list(proc.process_lines(lines))
    assert proc.timestamps_warning is False


# ── malformed / non-JSON lines (lenient handling) ─────────────────────────────


def test_malformed_json_treated_as_plain_msg() -> None:
    lines = ["not-json at all"]
    out = _process(_opts(services=()), lines)
    assert out == ["not-json at all"]


def test_partial_json_no_svc_kept_when_no_service_filter() -> None:
    lines = ['{"msg":"partial"}']
    out = _process(_opts(services=()), lines)
    assert "partial" in out[0]


def test_partial_json_no_svc_dropped_by_service_filter() -> None:
    """A line without a `svc` field is dropped when a service filter is active."""
    lines = ['{"msg":"no-svc"}']
    out = _process(_opts(services=("api",)), lines)
    assert out == []


def test_empty_line_does_not_crash() -> None:
    lines = [""]
    out = _process(_opts(services=()), lines)
    # Empty line produces an empty-ish output or is lenient — no crash.
    assert isinstance(out, list)


# ── multi-service prefix rule ─────────────────────────────────────────────────


def test_svc_prefix_only_when_multiple_services_in_options() -> None:
    """Single explicit service → no prefix. All/multi explicit → prefix."""
    lines = ['{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"msg"}']
    # Single explicit service → no svc prefix.
    out_single = _process(_opts(services=("api",)), lines)
    assert out_single == ["msg"]

    # Empty (all) services request → multi-service scope → prefix applied.
    out_all = _process(_opts(services=()), lines)
    assert "api |" in out_all[0]

    # Two explicit services → multi-service scope → prefix applied.
    out_multi = _process(_opts(services=("api", "db")), lines)
    assert "api |" in out_multi[0]
