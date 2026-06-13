from __future__ import annotations

import subprocess
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from winter_cli.core.subprocess_runner import IStreamingProcess, ISubprocessRunner, SubprocessResult


class _StreamingProcess:
    """Wraps `subprocess.Popen` so callers see only `stdout_lines` + `wait()`.

    Merged stdout+stderr; the runner always sets `stderr=STDOUT` because every
    consumer in winter wants interleaved output through a single reporter.
    """

    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self._proc = proc

    @property
    def stdout_lines(self) -> Iterator[str]:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            yield line.rstrip("\n")

    def wait(self) -> int:
        return self._proc.wait()


class LocalSubprocessRunner:
    """`subprocess` adapter for ISubprocessRunner.

    All `subprocess.run` / `subprocess.Popen` usage is confined here.
    Subprocesses inherit the parent environment unless `env` is supplied;
    callers wanting an empty env pass `env={}`.
    """

    @staticmethod
    def run(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> SubprocessResult:
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd is not None else None,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return SubprocessResult(returncode=-1, stdout="", stderr=str(exc))
        return SubprocessResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    @staticmethod
    def call(
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        """Run a process with inherited stdio, returning only the exit code.

        No `capture_output` and no stream redirection: stdin/stdout/stderr are
        inherited from this process, so the child writes straight to the
        terminal (TTY, colors, and stdout/stderr separation preserved). An
        exec failure (missing or non-executable file) surfaces as `126`, the
        shell convention for "command found but not executable".
        """
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd is not None else None,
                env=dict(env) if env is not None else None,
                check=False,
            )
        except OSError:
            return 126
        return completed.returncode

    @staticmethod
    @contextmanager
    def _popen_cm(
        cmd: list[str] | str,
        cwd: Path | None,
        env: Mapping[str, str] | None,
        shell: bool,
        merge_stderr: bool,
    ) -> Iterator[IStreamingProcess]:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            shell=shell,
            stdout=subprocess.PIPE,
            # When merge_stderr=True (default), merge stderr into stdout so
            # callers see a single interleaved stream (init/destroy hook flow).
            # When merge_stderr=False, leave stderr=None so it inherits the
            # parent's stderr fd — the orchestrator's diagnostics reach the
            # terminal without corrupting the NDJSON stdout (logs flow).
            stderr=subprocess.STDOUT if merge_stderr else None,
            text=True,
            bufsize=1,
        )
        try:
            yield _StreamingProcess(proc)
        finally:
            if proc.poll() is None:
                proc.wait()

    def popen(
        self,
        cmd: list[str] | str,
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        shell: bool = False,
        merge_stderr: bool = True,
    ) -> AbstractContextManager[IStreamingProcess]:
        return self._popen_cm(cmd, cwd, env, shell, merge_stderr)


def _conforms_local_subprocess_runner(x: LocalSubprocessRunner) -> ISubprocessRunner:
    return x
