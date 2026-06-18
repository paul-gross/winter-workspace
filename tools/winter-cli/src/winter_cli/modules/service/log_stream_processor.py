from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable, Iterator
from datetime import datetime

from winter_cli.modules.service.models import LogOptions, parse_rfc3339
from winter_cli.modules.workspace.pattern_match import is_single_literal_pattern, matches_any_pattern


class LogStreamProcessor:
    """Pure NDJSON-to-plain-line processor for `winter service logs`.

    Given a LogOptions and an iterable of raw stdout lines from the orchestrator,
    this class filters and renders each line according to the winter-defined
    contract and yields plain strings ready to write to the caller's stdout.

    Each NDJSON line must carry an `env` field in addition to `svc`/`msg` (and
    optional `ts`). The backstop filter matches `<env>/<svc>` against
    `options.patterns` via matches_any_pattern; lines missing `env` or `svc` are
    dropped when a filter is active (patterns non-empty).

    It also accumulates warnings (emitted once to stderr by the caller):
      - `timestamps_warning`: set if `-t` was requested but at least one line had no ts.
      - `time_filter_warning`: set if --since/--until was requested but at least
        one line had no ts (time filter was partial/skipped for those lines).

    The caller drives iteration; this class stays pure and clock-free (it receives
    the since/until thresholds already parsed into datetime objects).

    Tail backstop: when `options.follow` is False, rendered lines are buffered in a
    ring buffer (deque(maxlen=N)) and only emitted when `finalize()` is called.
    When `options.follow` is True, lines are yielded immediately and tail is NOT
    re-applied here (the orchestrator is expected to honour WINTER_LOG_TAIL).
    """

    def __init__(
        self,
        options: LogOptions,
        since_dt: datetime | None = None,
        until_dt: datetime | None = None,
    ) -> None:
        self._options = options
        # Accept pre-parsed datetimes when supplied; otherwise parse from the
        # options fields directly (avoids redundant parse at the call site).
        self._since_dt = since_dt if since_dt is not None else (
            parse_rfc3339(options.since_rfc3339) if options.since_rfc3339 else None
        )
        self._until_dt = until_dt if until_dt is not None else (
            parse_rfc3339(options.until_rfc3339) if options.until_rfc3339 else None
        )
        self._multi_service = not is_single_literal_pattern(options.patterns)

        # Ring buffer for tail backstop (non-follow mode only).
        tail = options.tail
        if not options.follow and tail != "all":
            assert isinstance(tail, int)
            self._buffer: deque[str] | None = deque(maxlen=tail)
        else:
            self._buffer = None

        # Warning state — flipped at most once per run.
        self.timestamps_warning = False
        self.time_filter_warning = False

    def process_lines(self, raw_lines: Iterable[str]) -> Iterator[str]:
        """Yield rendered plain-text lines, applying all filters.

        In follow mode, lines are yielded immediately.
        In non-follow mode, they are buffered; call `finalize()` after the
        iterable is exhausted to flush the ring buffer.
        """
        patterns: tuple[str, ...] = tuple(self._options.patterns)
        for raw in raw_lines:
            raw = raw.rstrip("\n")
            rendered = self._process_one(raw, patterns)
            if rendered is None:
                continue
            if self._buffer is not None:
                # Non-follow: accumulate in ring buffer.
                self._buffer.append(rendered)
            else:
                yield rendered

    def finalize(self) -> Iterator[str]:
        """Flush the tail ring buffer (non-follow mode only).

        Call after exhausting `process_lines`. In follow mode this is a no-op.
        """
        if self._buffer is not None:
            yield from self._buffer

    def _process_one(self, raw: str, patterns: tuple[str, ...]) -> str | None:
        """Parse, filter, and render one raw line. Returns None to drop."""
        # Parse the NDJSON line; treat non-JSON leniently as plain msg.
        ts_str: str | None = None
        env: str | None = None
        svc: str | None = None
        msg: str = raw

        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                ts_str = obj.get("ts") if isinstance(obj.get("ts"), str) else None
                env = obj.get("env") if isinstance(obj.get("env"), str) else None
                svc = obj.get("svc") if isinstance(obj.get("svc"), str) else None
                msg = str(obj.get("msg", raw))
        except (json.JSONDecodeError, ValueError):
            pass  # lenient: keep the whole raw line as msg

        # Backstop service filter: when patterns are active, keep the line only if
        # both env and svc are present and match at least one pattern. Drop lines
        # missing env or svc when a filter is active.
        if patterns and (env is None or svc is None or not matches_any_pattern(env, svc, patterns)):
            return None

        # Time filters (only applied to lines that have a parseable ts).
        ts_dt: datetime | None = None
        if ts_str is not None:
            ts_dt = parse_rfc3339(ts_str)

        if self._since_dt is not None or self._until_dt is not None:
            if ts_dt is None:
                # Can't time-filter this line — keep it but note the warning.
                self.time_filter_warning = True
            else:
                if self._since_dt is not None and ts_dt < self._since_dt:
                    return None
                if self._until_dt is not None and ts_dt > self._until_dt:
                    return None

        # Render the plain-text line.
        parts: list[str] = []

        if self._options.timestamps:
            if ts_dt is not None:
                parts.append(ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
            else:
                # -t requested but no ts — note warning, omit the ts field.
                self.timestamps_warning = True

        if self._multi_service and env is not None and svc is not None:
            parts.append(f"{env}/{svc} |")

        parts.append(msg)

        return " ".join(parts)
