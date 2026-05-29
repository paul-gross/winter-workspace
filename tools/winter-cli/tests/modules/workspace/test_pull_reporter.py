"""Tests for `pull_reporter.{Stream,Json}PullReporter`.

`ws pull` now reports the number of commits integrated on a *successful*
fast-forward / merge / rebase (not only the ahead/behind span on
divergence). Pin both the human form (`fast-forwarded (+N)`, `merged (+N)`,
`rebased (+N)`, `up to date`) and the NDJSON envelope.
"""

from __future__ import annotations

import json

from winter_cli.modules.workspace.models import SyncResult
from winter_cli.modules.workspace.pull_reporter import (
    IPullReporter,
    JsonPullReporter,
    StreamPullReporter,
)


class _CapturingClick:
    """Minimal click stand-in — records every echo for inspection."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, bool]] = []

    def echo(self, message: str, err: bool = False) -> None:
        self.lines.append((message, err))


def _conforms_stream_reporter(x: StreamPullReporter) -> IPullReporter:
    return x


def _conforms_json_reporter(x: JsonPullReporter) -> IPullReporter:
    return x


# --- stream reporter ----------------------------------------------------------


def test_stream_repo_synced_integrate_outcomes_carry_commit_count() -> None:
    """ff / merge / rebase each report how many commits they brought in."""
    click = _CapturingClick()
    reporter = StreamPullReporter(click)

    reporter.repo_synced("alpha", "demo", SyncResult.fast_forwarded, commits=3, ahead=0, behind=0)
    reporter.repo_synced("alpha", "demo", SyncResult.merged, commits=2, ahead=0, behind=0)
    reporter.repo_synced("alpha", "demo", SyncResult.rebased, commits=4, ahead=0, behind=0)

    assert click.lines == [
        ("[alpha/demo] fast-forwarded (+3)", False),
        ("[alpha/demo] merged (+2)", False),
        ("[alpha/demo] rebased (+4)", False),
    ]


def test_stream_repo_synced_up_to_date_has_no_count() -> None:
    click = _CapturingClick()
    reporter = StreamPullReporter(click)

    reporter.repo_synced("alpha", "demo", SyncResult.up_to_date, commits=0, ahead=0, behind=0)

    assert click.lines == [("[alpha/demo] up to date", False)]


def test_stream_repo_synced_diverged_to_stderr_with_span() -> None:
    click = _CapturingClick()
    reporter = StreamPullReporter(click)

    reporter.repo_synced("alpha", "demo", SyncResult.diverged, commits=0, ahead=3, behind=2)

    assert click.lines == [("[alpha/demo] diverged: +3/-2", True)]


# --- json reporter ------------------------------------------------------------


def test_json_repo_synced_full_envelope_carries_commits() -> None:
    """Lock the NDJSON envelope: type, scope, repo, result, commits, ahead, behind."""
    click = _CapturingClick()
    reporter = JsonPullReporter(click)

    reporter.repo_synced("alpha", "demo", SyncResult.fast_forwarded, commits=3, ahead=0, behind=0)

    payload = json.loads(click.lines[0][0])
    assert payload == {
        "type": "repo_synced",
        "scope": "alpha",
        "repo": "demo",
        "result": "fast_forwarded",
        "commits": 3,
        "ahead": 0,
        "behind": 0,
    }
