from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable, Iterator
from datetime import datetime

from winter_cli.modules.service.models import LogOptions, parse_rfc3339


class LogStreamProcessor:
    """Pure NDJSON-to-plain-line processor for `winter service logs`.

    Given a LogOptions and an iterable of raw stdout lines from the orchestrator,
    this class filters and renders each line according to the winter-defined
    contract and yields plain strings ready to write to the caller's stdout.

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
        since_dt: datetime | None,
        until_dt: datetime | None,
    ) -> None:
        self._options = options
        self._since_dt = since_dt
        self._until_dt = until_dt
        self._multi_service = len(options.services) != 1

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
        options = self._options
        services_set = set(options.services)
        for raw in raw_lines:
            raw = raw.rstrip("\n")
            rendered = self._process_one(raw, services_set)
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

    def _process_one(self, raw: str, services_set: set[str]) -> str | None:
        """Parse, filter, and render one raw line. Returns None to drop."""
        # Parse the NDJSON line; treat non-JSON leniently as plain msg.
        ts_str: str | None = None
        svc: str | None = None
        msg: str = raw

        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                ts_str = obj.get("ts") if isinstance(obj.get("ts"), str) else None
                svc = obj.get("svc") if isinstance(obj.get("svc"), str) else None
                msg = str(obj.get("msg", raw))
        except (json.JSONDecodeError, ValueError):
            pass  # lenient: keep the whole raw line as msg

        # Service filter: if services requested and this line's svc is not in set, drop.
        if services_set and svc not in services_set:
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

        if self._multi_service and svc is not None:
            parts.append(f"{svc} |")

        parts.append(msg)

        return " ".join(parts)
