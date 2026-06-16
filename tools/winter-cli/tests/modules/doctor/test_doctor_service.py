from __future__ import annotations

from typing import Any

from winter_cli.modules.doctor.doctor_service import DoctorService
from winter_cli.modules.doctor.models import ProbeResult, ProbeStatus


class _FakeCore:
    def __init__(self, results: list[ProbeResult]) -> None:
        self._results = results

    def run(self) -> list[ProbeResult]:
        return list(self._results)


class _FakeWorkspace:
    def __init__(self, results: list[ProbeResult]) -> None:
        self._results = results

    def run(self) -> list[ProbeResult]:
        return list(self._results)


class _FakeExtensions:
    def __init__(self, results: list[ProbeResult]) -> None:
        self._results = results
        self.calls: list[Any] = []

    def run(self, standalone_repos: Any) -> list[ProbeResult]:
        self.calls.append(standalone_repos)
        return list(self._results)


class _FakeCapabilities:
    def __init__(self, results: list[ProbeResult] | None = None) -> None:
        self._results = results or []

    def run(self) -> list[ProbeResult]:
        return list(self._results)


class _FakeRepoFactory:
    def get_standalone_repos(self) -> list[str]:
        return ["repo-a"]


class _RecordingReporter:
    def __init__(self) -> None:
        self.started_calls = 0
        self.results: list[ProbeResult] = []
        self.finished_summary: tuple[int, int, int] | None = None

    def started(self) -> None:
        self.started_calls += 1

    def probe_result(self, result: ProbeResult) -> None:
        self.results.append(result)

    def finished(self, total: int, fails: int, warns: int) -> None:
        self.finished_summary = (total, fails, warns)


def _make(status: ProbeStatus, name: str = "probe") -> ProbeResult:
    return ProbeResult(source="core", name=name, status=status)


def test_emits_each_result_and_returns_zero_exit_when_no_fails() -> None:
    core = _FakeCore([_make(ProbeStatus.pass_), _make(ProbeStatus.warn)])
    exts = _FakeExtensions([_make(ProbeStatus.pass_)])
    svc = DoctorService(core, _FakeWorkspace([]), exts, _FakeRepoFactory(), _FakeCapabilities())  # type: ignore[arg-type]
    reporter = _RecordingReporter()

    summary = svc.run(reporter)  # type: ignore[arg-type]

    assert reporter.started_calls == 1
    assert len(reporter.results) == 3
    assert reporter.finished_summary == (3, 0, 1)
    assert summary.total == 3
    assert summary.fails == 0
    assert summary.warns == 1
    assert summary.exit_code == 0


def test_any_fail_flips_exit_code_to_one() -> None:
    core = _FakeCore([_make(ProbeStatus.pass_), _make(ProbeStatus.fail)])
    exts = _FakeExtensions([])
    svc = DoctorService(core, _FakeWorkspace([]), exts, _FakeRepoFactory(), _FakeCapabilities())  # type: ignore[arg-type]
    reporter = _RecordingReporter()

    summary = svc.run(reporter)  # type: ignore[arg-type]
    assert summary.exit_code == 1
    assert summary.fails == 1


def test_passes_standalone_repos_to_extension_runner() -> None:
    exts = _FakeExtensions([])
    svc = DoctorService(_FakeCore([]), _FakeWorkspace([]), exts, _FakeRepoFactory(), _FakeCapabilities())  # type: ignore[arg-type]
    svc.run(_RecordingReporter())  # type: ignore[arg-type]
    assert exts.calls == [["repo-a"]]


def test_workspace_probe_results_appear_between_core_and_extensions() -> None:
    core = _FakeCore([ProbeResult(source="core", name="c", status=ProbeStatus.pass_)])
    workspace = _FakeWorkspace([ProbeResult(source="project", name="p", status=ProbeStatus.pass_)])
    exts = _FakeExtensions([ProbeResult(source="ext", name="e", status=ProbeStatus.pass_)])
    svc = DoctorService(core, workspace, exts, _FakeRepoFactory(), _FakeCapabilities())  # type: ignore[arg-type]
    reporter = _RecordingReporter()

    svc.run(reporter)  # type: ignore[arg-type]
    assert [r.source for r in reporter.results] == ["core", "project", "ext"]


def test_capability_probe_results_flow_into_aggregate() -> None:
    cap_result = ProbeResult(source="capabilities", name="slot: service", status=ProbeStatus.pass_)
    caps = _FakeCapabilities([cap_result])
    svc = DoctorService(_FakeCore([]), _FakeWorkspace([]), _FakeExtensions([]), _FakeRepoFactory(), caps)  # type: ignore[arg-type]
    reporter = _RecordingReporter()

    summary = svc.run(reporter)  # type: ignore[arg-type]

    assert cap_result in reporter.results
    assert summary.total == 1
    assert summary.exit_code == 0


def test_capability_fail_bumps_exit_code() -> None:
    cap_result = ProbeResult(source="capabilities", name="slot: service", status=ProbeStatus.fail)
    caps = _FakeCapabilities([cap_result])
    svc = DoctorService(_FakeCore([]), _FakeWorkspace([]), _FakeExtensions([]), _FakeRepoFactory(), caps)  # type: ignore[arg-type]
    reporter = _RecordingReporter()

    summary = svc.run(reporter)  # type: ignore[arg-type]

    assert summary.fails == 1
    assert summary.exit_code == 1
