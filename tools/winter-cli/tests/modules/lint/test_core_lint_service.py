from __future__ import annotations

import sys
from pathlib import Path

from tests.conftest import FakeFilesystem, FakeSubprocessRunner
from winter_cli.core.subprocess_runner import SubprocessResult
from winter_cli.modules.lint.core_lint_service import (
    CORE_SOURCE,
    CoreLintService,
    default_extractability_script_path,
)
from winter_cli.modules.lint.models import LintScope, LintScopeKind, LintStatus

WORKSPACE_ROOT = Path("/ws")
SCRIPT_PATH = Path("/cli/tools/winter-lint/extractability.py")
SCOPE = LintScope(kind=LintScopeKind.all, label="all", paths=[WORKSPACE_ROOT])

# The fake runner keys responses by the joined command string.
_CMD_KEY = f"{sys.executable} {SCRIPT_PATH}"


def _build_service(
    *,
    files: dict[Path, str] | None = None,
    run_response: SubprocessResult | None = None,
) -> tuple[CoreLintService, FakeSubprocessRunner]:
    fs = FakeFilesystem(
        files=files if files is not None else {SCRIPT_PATH: ""},
        directories={WORKSPACE_ROOT},
    )
    responses: dict[str, SubprocessResult] = {}
    if run_response is not None:
        responses[_CMD_KEY] = run_response
    runner = FakeSubprocessRunner(run_responses=responses)
    svc = CoreLintService(
        workspace_root=WORKSPACE_ROOT,
        fs=fs,
        subprocess_runner=runner,
        winter_cli_path="/usr/bin/winter",
        script_path=SCRIPT_PATH,
    )
    return svc, runner


def test_runs_bundled_script_with_lint_env() -> None:
    svc, runner = _build_service(run_response=SubprocessResult(0, "", ""))
    svc.run(SCOPE)
    assert runner.run_calls[-1][0] == [sys.executable, str(SCRIPT_PATH)]
    assert runner.run_calls[-1][1] == WORKSPACE_ROOT
    env = runner.run_envs[-1]
    assert env is not None
    assert env["WINTER_CLI"] == "/usr/bin/winter"
    assert env["WINTER_WORKSPACE_DIR"] == str(WORKSPACE_ROOT)
    assert env["WINTER_LINT_SCOPE"] == "all"
    assert env["WINTER_LINT_PATHS"] == str(WORKSPACE_ROOT)


def test_parses_findings_under_core_source() -> None:
    svc, _ = _build_service(
        run_response=SubprocessResult(
            0,
            '{"check": "extractability", "status": "fail", "message": "layering", "file": "ai/x.md", "line": 3}\n',
            "",
        )
    )
    outcome = svc.run(SCOPE)
    assert outcome is not None
    assert outcome.source == CORE_SOURCE
    finding = outcome.findings[0]
    assert finding.source == CORE_SOURCE
    assert finding.check == "extractability"
    assert finding.status == LintStatus.fail
    assert finding.file == "ai/x.md"
    assert finding.line == 3


def test_clean_run_still_contributes_an_outcome() -> None:
    svc, _ = _build_service(run_response=SubprocessResult(0, "", ""))
    outcome = svc.run(SCOPE)
    assert outcome is not None
    assert outcome.source == CORE_SOURCE
    assert outcome.findings == []


def test_non_zero_exit_becomes_synthetic_fail() -> None:
    svc, _ = _build_service(run_response=SubprocessResult(1, "", "graph fetch failed"))
    outcome = svc.run(SCOPE)
    assert outcome is not None
    assert outcome.findings[0].status == LintStatus.fail
    assert outcome.findings[0].message == "graph fetch failed"


def test_missing_script_contributes_nothing() -> None:
    svc, runner = _build_service(files={})
    assert svc.run(SCOPE) is None
    assert runner.run_calls == []


def test_default_script_path_points_at_sibling_tools_dir() -> None:
    path = default_extractability_script_path()
    assert path.parts[-3:] == ("tools", "winter-lint", "extractability.py")
