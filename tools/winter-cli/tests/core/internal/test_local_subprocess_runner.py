from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from winter_cli.core.internal import local_subprocess_runner
from winter_cli.core.internal.local_subprocess_runner import LocalSubprocessRunner


def test_run_passes_cmd_cwd_env_to_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_subprocess = MagicMock()
    fake_subprocess.run.return_value = MagicMock(returncode=0, stdout="hello\n", stderr="")
    monkeypatch.setattr(local_subprocess_runner, "subprocess", fake_subprocess)

    result = LocalSubprocessRunner.run(["echo", "hi"], cwd=tmp_path, env={"K": "V"})

    fake_subprocess.run.assert_called_once_with(
        ["echo", "hi"],
        cwd=str(tmp_path),
        env={"K": "V"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "hello\n"


def test_run_without_cwd_or_env_passes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_subprocess = MagicMock()
    fake_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(local_subprocess_runner, "subprocess", fake_subprocess)

    result = LocalSubprocessRunner.run(["git", "status"])

    fake_subprocess.run.assert_called_once_with(
        ["git", "status"],
        cwd=None,
        env=None,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_run_returns_failure_result_when_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_subprocess = MagicMock()
    fake_subprocess.run.side_effect = OSError("no such file")
    monkeypatch.setattr(local_subprocess_runner, "subprocess", fake_subprocess)

    result = LocalSubprocessRunner.run(["does-not-exist"])

    assert result.returncode == -1
    assert result.stdout == ""
    assert "no such file" in result.stderr


def test_popen_passes_cmd_cwd_env_shell_to_popen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_proc = MagicMock()
    fake_proc.stdout = iter(["line1\n", "line2\n"])
    fake_proc.wait.return_value = 0
    fake_proc.poll.return_value = 0

    fake_subprocess = MagicMock()
    fake_subprocess.Popen.return_value = fake_proc
    fake_subprocess.PIPE = -1
    fake_subprocess.STDOUT = -2
    monkeypatch.setattr(local_subprocess_runner, "subprocess", fake_subprocess)

    runner = LocalSubprocessRunner()
    with runner.popen(["bash", "-c", "echo hi"], cwd=tmp_path, env={"X": "1"}, shell=False) as proc:
        lines = list(proc.stdout_lines)

    fake_subprocess.Popen.assert_called_once_with(
        ["bash", "-c", "echo hi"],
        cwd=str(tmp_path),
        env={"X": "1"},
        shell=False,
        stdout=fake_subprocess.PIPE,
        stderr=fake_subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert lines == ["line1", "line2"]
