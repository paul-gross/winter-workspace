from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.service.log_stream_processor import LogStreamProcessor
from winter_cli.modules.service.models import LogOptions
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver


class ServiceLogsService:
    """Streams logs from the registered orchestrator via the winter-defined contract.

    Invokes the orchestrator entrypoint as `<entrypoint> logs <pattern...>` with
    `cwd` at the workspace root. The `<env>/<service>` selection patterns are
    forwarded verbatim as positional argv tokens. Render parameters are conveyed
    via WINTER_LOG_* environment variables (WINTER_LOG_FOLLOW, WINTER_LOG_TAIL,
    WINTER_LOG_SINCE, WINTER_LOG_UNTIL, WINTER_LOG_TIMESTAMPS). Like every
    dispatch it also exports `WINTER_WORKSPACE_DIR`, `WINTER_EXT_DIR`, and
    `WINTER_EXT_PREFIX`. The orchestrator's stdout is read as NDJSON; each line
    must carry an `env` field in addition to `svc`/`msg`; winter applies a
    segment-aware backstop filter matching `<env>/<svc>` against the requested
    patterns, then applies time/tail filters and renders plain lines to stdout.
    The orchestrator's stderr inherits the parent's fd so diagnostics reach the
    terminal without corrupting the NDJSON stream.

    Returns the orchestrator's exit code, or 130 if interrupted by KeyboardInterrupt.
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        orchestrator_resolver: ServiceOrchestratorResolver,
        click: Any,
        workspace_root: Path,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._orchestrator_resolver = orchestrator_resolver
        self._click = click
        self._workspace_root = workspace_root

    def stream(self, options: LogOptions) -> int:
        """Run the orchestrator logs entrypoint and stream rendered output to stdout."""
        resolved = self._orchestrator_resolver.resolve()
        cmd = [str(resolved.entrypoint), "logs", *options.patterns]

        # Build env vars for the orchestrator.
        extra_env = dict(os.environ)
        extra_env["WINTER_LOG_FOLLOW"] = "1" if options.follow else "0"
        extra_env["WINTER_LOG_TAIL"] = str(options.tail)
        extra_env["WINTER_LOG_SINCE"] = options.since_rfc3339
        extra_env["WINTER_LOG_UNTIL"] = options.until_rfc3339
        extra_env["WINTER_LOG_TIMESTAMPS"] = "1" if options.timestamps else "0"
        extra_env["WINTER_WORKSPACE_DIR"] = str(self._workspace_root)
        extra_env["WINTER_EXT_DIR"] = str(resolved.ext_dir)
        extra_env["WINTER_EXT_PREFIX"] = resolved.prefix

        processor = LogStreamProcessor(options)

        exit_code = 0
        try:
            with self._subprocess_runner.popen(
                cmd, cwd=self._workspace_root, env=extra_env, merge_stderr=False
            ) as proc:
                try:
                    for rendered in processor.process_lines(proc.stdout_lines):
                        self._click.echo(rendered)
                except KeyboardInterrupt:
                    return 130

                # Flush tail ring buffer (no-op in follow mode).
                for rendered in processor.finalize():
                    self._click.echo(rendered)

                exit_code = proc.wait()
        except KeyboardInterrupt:
            return 130

        # Emit accumulated warnings (once each) to stderr.
        if processor.timestamps_warning:
            self._click.echo(
                "warning: the orchestrator supplies no per-line timestamps — "
                "timestamp prefixes omitted for affected lines",
                err=True,
            )
        if processor.time_filter_warning:
            self._click.echo(
                "warning: the orchestrator supplies no per-line timestamps — "
                "--since/--until filter is partial (applied only to lines with a ts field)",
                err=True,
            )

        return exit_code
