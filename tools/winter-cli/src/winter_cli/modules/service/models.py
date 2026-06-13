from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime

# Duration pattern: number followed by s/m/h/d
_DURATION_RE = re.compile(r"^(\d+)([smhd])$")
_DURATION_SECONDS: dict[str, int] = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_rfc3339(value: str) -> datetime | None:
    """Parse an RFC3339 timestamp string into a UTC datetime, or return None.

    Normalises the Z suffix before calling fromisoformat so both
    '2026-06-13T10:00:00Z' and '2026-06-13T10:00:00+00:00' are accepted.
    Returns None on any parse failure.
    """
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, AttributeError):
        return None


def parse_since_until(value: str, now: datetime) -> str:
    """Parse a duration (90s, 5m, 2h, 3d) or RFC3339 timestamp into an RFC3339 string.

    Durations are normalized to an absolute threshold relative to `now`.
    The returned string is always UTC with a Z suffix, suitable for
    WINTER_LOG_SINCE / WINTER_LOG_UNTIL env vars.

    Raises ValueError on unrecognised input.
    """
    m = _DURATION_RE.match(value.strip())
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        delta_s = amount * _DURATION_SECONDS[unit]
        threshold = datetime.fromtimestamp(now.timestamp() - delta_s, tz=UTC)
        return threshold.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Try RFC3339 parse.
    dt = parse_rfc3339(value)
    if dt is not None:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError(
        f"invalid --since/--until value {value!r}: expected a duration (90s, 5m, 2h, 3d) or an RFC3339 timestamp"
    )


@dataclasses.dataclass(frozen=True)
class LogOptions:
    """Parsed options for `winter service logs`.

    `services` is a tuple of zero or more explicit service names — empty means all.
    `follow` streams until interrupted.
    `tail` is either an integer (last N lines) or the string 'all'.
    `since_rfc3339` / `until_rfc3339` are normalised RFC3339 strings or empty.
    `timestamps` enables per-line timestamp prefixing.
    """

    services: tuple[str, ...]
    follow: bool
    tail: int | str  # int or "all"
    since_rfc3339: str  # empty string = unset
    until_rfc3339: str  # empty string = unset
    timestamps: bool
