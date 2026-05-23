from __future__ import annotations

from pathlib import Path

import git
import pytest

from winter_cli.modules.workspace.internal.git_ops_service import (
    BASE_DELAY_S,
    DELAY_CAP_S,
    JITTER_RATIO,
    GitOpsService,
    is_transient_git_error,
)
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.models import RepoError


def _git_err(stderr: str) -> git.GitCommandError:
    """Build a `GitCommandError` with the given stderr; exit code 128."""
    return git.GitCommandError(("git", "fetch", "origin"), 128, stderr=stderr)


# ------------------------------ classifier ---------------------------------


@pytest.mark.parametrize(
    "stderr",
    [
        "Connection closed by 217.197.84.140 port 22",
        "fatal: the remote end hung up unexpectedly",
        "kex_exchange_identification: Connection closed by remote host",
        "ssh: connect to host codeberg.org port 22: Connection timed out",
        # case-insensitive match
        "CONNECTION CLOSED BY 217.197.84.140 PORT 22",
    ],
)
def test_is_transient_git_error_matches_documented_patterns(stderr: str):
    assert is_transient_git_error(_git_err(stderr))


@pytest.mark.parametrize(
    "stderr",
    [
        "fatal: Authentication failed",
        "fatal: repository 'foo' does not exist",
        "! [rejected] main -> main (non-fast-forward)",
        "fatal: Could not read from remote repository.",
        "",
    ],
)
def test_is_transient_git_error_rejects_non_transient(stderr: str):
    assert not is_transient_git_error(_git_err(stderr))


# ------------------------------ run_remote ---------------------------------


def _service(sleeps: list[float]) -> GitOpsService:
    """A service with no real sleeps; sleep durations get recorded in `sleeps`."""
    return GitOpsService(
        RepoErrorFactory(),
        sleep=lambda d: sleeps.append(d),
        jitter=lambda: 0.0,  # deterministic — base delay only
    )


def test_run_remote_returns_value_on_success(tmp_path: Path):
    sleeps: list[float] = []
    svc = _service(sleeps)
    assert svc.run_remote(lambda: "ok", cwd=tmp_path, message="x") == "ok"
    assert sleeps == []  # no retry, no sleep


def test_run_remote_retries_transient_up_to_max_attempts(tmp_path: Path):
    sleeps: list[float] = []
    svc = _service(sleeps)
    transient = _git_err("Connection closed by 1.2.3.4 port 22")
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise transient

    with pytest.raises(RepoError) as ei:
        svc.run_remote(op, cwd=tmp_path, message="fetch failed")
    assert calls["n"] == svc.MAX_ATTEMPTS  # 3 attempts
    assert len(sleeps) == svc.MAX_ATTEMPTS - 1  # sleeps between attempts only
    # Final RepoError carries the last gitpython error's context.
    assert ei.value.subcommand == "fetch"
    assert "Connection closed" in (ei.value.stderr or "")


def test_run_remote_succeeds_after_transient_then_success(tmp_path: Path):
    sleeps: list[float] = []
    svc = _service(sleeps)
    sequence = [_git_err("Connection closed by 1.2.3.4 port 22"), None]
    calls = {"n": 0}

    def op():
        i = calls["n"]
        calls["n"] += 1
        item = sequence[i]
        if isinstance(item, BaseException):
            raise item
        return "recovered"

    assert svc.run_remote(op, cwd=tmp_path, message="fetch failed") == "recovered"
    assert calls["n"] == 2
    assert len(sleeps) == 1  # one retry, one sleep


def test_run_remote_does_not_retry_non_transient(tmp_path: Path):
    sleeps: list[float] = []
    svc = _service(sleeps)
    non_transient = _git_err("fatal: Authentication failed")
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise non_transient

    with pytest.raises(RepoError):
        svc.run_remote(op, cwd=tmp_path, message="push failed")
    assert calls["n"] == 1
    assert sleeps == []


def test_run_remote_backoff_respects_cap_and_jitter(tmp_path: Path):
    # jitter=+1.0 pushes each delay to the upper bound of its jitter band.
    svc = GitOpsService(
        RepoErrorFactory(),
        sleep=lambda _d: None,
        jitter=lambda: 1.0,
    )
    # base*(1+JITTER_RATIO) for attempt 1, capped at DELAY_CAP_S thereafter.
    assert svc._backoff_delay(1) == pytest.approx(BASE_DELAY_S * (1 + JITTER_RATIO))
    # exponential growth, capped at DELAY_CAP_S
    for attempt in range(1, 10):
        assert 0 <= svc._backoff_delay(attempt) <= DELAY_CAP_S


def test_executor_uses_parallelism_constant():
    svc = GitOpsService(RepoErrorFactory())
    with svc.executor() as pool:
        assert pool._max_workers == GitOpsService.PARALLELISM
