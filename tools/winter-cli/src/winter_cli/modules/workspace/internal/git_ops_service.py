from __future__ import annotations

import concurrent.futures
import contextlib
import logging
import random
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeVar

import git

from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory

logger = logging.getLogger(__name__)


# Codeberg.org (and most SSH-based git hosts) throttle simultaneous SSH
# connections per source IP. Empirically the cap is around 5; staying at 4
# keeps a comfortable margin while still parallelizing 4x over serial git ops.
PARALLELISM: int = 4

# Retry policy for transient network errors. Gentle defaults — these absorb
# transient SSH-cap collisions, not sustained outages.
MAX_ATTEMPTS: int = 3
BASE_DELAY_S: float = 1.0
DELAY_CAP_S: float = 8.0
JITTER_RATIO: float = 0.5  # ±50% jitter


_TRANSIENT_STDERR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"Connection closed by .* port 22",
        r"fatal: the remote end hung up unexpectedly",
        r"kex_exchange_identification",
        r"Connection timed out",
    )
)


T = TypeVar("T")


def is_transient_git_error(exc: git.GitCommandError) -> bool:
    """Whether `exc`'s stderr matches a known transient SSH/network failure.

    Only the symptoms we've actually seen on Codeberg under load are listed —
    auth failures, ref refusals, and divergence are deliberately excluded so
    they fail fast.
    """
    stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    return any(pat.search(stderr) for pat in _TRANSIENT_STDERR_PATTERNS)


class GitOpsService:
    """Centralized service for network-touching git operations.

    Owns the thread pool for parallel git work (via `executor()`) and the
    retry policy for transient SSH errors (via `run_remote()`). Local git
    ops stay as direct `r.git.<verb>` calls in the repositories — they
    don't fail transiently and gain nothing from going through a service.
    """

    PARALLELISM: int = PARALLELISM
    MAX_ATTEMPTS: int = MAX_ATTEMPTS

    def __init__(
        self,
        error_factory: RepoErrorFactory,
        *,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._error_factory = error_factory
        self._sleep = sleep
        self._jitter = jitter or (lambda: random.uniform(-1.0, 1.0))

    @contextlib.contextmanager
    def executor(self) -> Iterator[concurrent.futures.ThreadPoolExecutor]:
        """Thread pool capped at PARALLELISM for fan-out of git operations."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.PARALLELISM) as pool:
            yield pool

    def run_remote(
        self,
        op: Callable[[], T],
        *,
        cwd: Path | str,
        message: str,
    ) -> T:
        """Run a network-touching git op with bounded retry on transient errors.

        Caller passes the actual git call as a thunk —
        `lambda: r.git.fetch("origin")`. Retries up to `MAX_ATTEMPTS`
        times when the failure's stderr matches a known transient SSH
        pattern (see `is_transient_git_error`); between attempts, sleeps
        a jittered exponential backoff capped at `DELAY_CAP_S`. Retries
        are silent — the caller observes one logical outcome, not
        per-attempt status. Non-transient failures (auth, missing repo,
        refused ref) raise after the first attempt.
        """
        last_exc: git.GitCommandError | None = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                return op()
            except git.GitCommandError as exc:
                last_exc = exc
                if attempt >= self.MAX_ATTEMPTS or not is_transient_git_error(exc):
                    break
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "transient git error (attempt %d/%d): %s — retrying in %.2fs",
                    attempt,
                    self.MAX_ATTEMPTS,
                    exc.stderr.strip() if isinstance(exc.stderr, str) else "",
                    delay,
                )
                self._sleep(delay)
        assert last_exc is not None  # loop entered ≥ once, only exits on success/break
        raise self._error_factory.from_git(last_exc, message=message, cwd=cwd) from last_exc

    def _backoff_delay(self, attempt: int) -> float:
        """Jittered exponential backoff: base*2^(attempt-1), capped, ±JITTER_RATIO."""
        base = min(BASE_DELAY_S * (2 ** (attempt - 1)), DELAY_CAP_S)
        delay = base + base * JITTER_RATIO * self._jitter()
        return max(0.0, min(delay, DELAY_CAP_S))
