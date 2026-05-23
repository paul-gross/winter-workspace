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

_CWD = Path("/tmp")


def _git_err(stderr: str) -> git.GitCommandError:
    return git.GitCommandError(("git", "fetch", "origin"), 128, stderr=stderr)


# ── is_transient_git_error ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stderr",
    [
        "Connection closed by 217.197.84.140 port 22",
        "fatal: the remote end hung up unexpectedly",
        "kex_exchange_identification: Connection closed by remote host",
        "ssh: connect to host codeberg.org port 22: Connection timed out",
        "CONNECTION CLOSED BY 217.197.84.140 PORT 22",
    ],
)
def test_is_transient_git_error_matches_documented_patterns(stderr: str) -> None:
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
def test_is_transient_git_error_rejects_non_transient(stderr: str) -> None:
    assert not is_transient_git_error(_git_err(stderr))


# ── run_remote ─────────────────────────────────────────────────────────────


def _service(sleeps: list[float]) -> GitOpsService:
    return GitOpsService(
        RepoErrorFactory(),
        sleep=lambda d: sleeps.append(d),
        jitter=lambda: 0.0,
    )


def test_run_remote_returns_value_on_success() -> None:
    sleeps: list[float] = []
    svc = _service(sleeps)
    assert svc.run_remote(lambda: "ok", cwd=_CWD, message="x") == "ok"
    assert sleeps == []


def test_run_remote_retries_transient_up_to_max_attempts() -> None:
    sleeps: list[float] = []
    svc = _service(sleeps)
    transient = _git_err("Connection closed by 1.2.3.4 port 22")
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise transient

    with pytest.raises(RepoError) as ei:
        svc.run_remote(op, cwd=_CWD, message="fetch failed")
    assert calls["n"] == svc.MAX_ATTEMPTS
    assert len(sleeps) == svc.MAX_ATTEMPTS - 1
    assert ei.value.subcommand == "fetch"
    assert "Connection closed" in (ei.value.stderr or "")


def test_run_remote_succeeds_after_transient_then_success() -> None:
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

    assert svc.run_remote(op, cwd=_CWD, message="fetch failed") == "recovered"
    assert calls["n"] == 2
    assert len(sleeps) == 1


def test_run_remote_does_not_retry_non_transient() -> None:
    sleeps: list[float] = []
    svc = _service(sleeps)
    non_transient = _git_err("fatal: Authentication failed")
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise non_transient

    with pytest.raises(RepoError):
        svc.run_remote(op, cwd=_CWD, message="push failed")
    assert calls["n"] == 1
    assert sleeps == []


def test_run_remote_backoff_respects_cap_and_jitter() -> None:
    svc = GitOpsService(
        RepoErrorFactory(),
        sleep=lambda _d: None,
        jitter=lambda: 1.0,
    )
    assert svc._backoff_delay(1) == pytest.approx(BASE_DELAY_S * (1 + JITTER_RATIO))
    for attempt in range(1, 10):
        assert 0 <= svc._backoff_delay(attempt) <= DELAY_CAP_S


# ── executor ───────────────────────────────────────────────────────────────


def test_executor_uses_parallelism_constant() -> None:
    svc = GitOpsService(RepoErrorFactory())
    with svc.executor() as pool:
        assert pool._max_workers == GitOpsService.PARALLELISM
