from __future__ import annotations

import os
from typing import Any

from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.service.log_stream_processor import LogStreamProcessor
from winter_cli.modules.service.models import LogOptions, parse_rfc3339
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver


class ServiceLogsService:
    """Streams logs from the registered orchestrator via the winter-defined contract.

    Invokes the orchestrator entrypoint as `<entrypoint> logs <env>`, conveying
    all log parameters via WINTER_LOG_* environment variables. The orchestrator's
    stdout is read as NDJSON; winter parses each line, applies idempotent backstop
    filters (service, time, tail), and renders plain lines to the caller's stdout.
    The orchestrator's stderr inherits the parent's fd so diagnostics reach the
    terminal without corrupting the NDJSON stream.

    Returns the orchestrator's exit code, or 130 if interrupted by KeyboardInterrupt.
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        orchestrator_resolver: ServiceOrchestratorResolver,
        click: Any,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._orchestrator_resolver = orchestrator_resolver
        self._click = click

    def stream(self, env: str, options: LogOptions) -> int:
        """Run the orchestrator logs entrypoint and stream rendered output to stdout."""
        entrypoint = self._orchestrator_resolver.resolve()
        cmd = [str(entrypoint), "logs", env]

        # Parse since/until RFC3339 strings into datetime objects for the processor.
        since_dt = parse_rfc3339(options.since_rfc3339) if options.since_rfc3339 else None
        until_dt = parse_rfc3339(options.until_rfc3339) if options.until_rfc3339 else None

        # Build env vars for the orchestrator.
        extra_env = dict(os.environ)
        extra_env["WINTER_LOG_SERVICES"] = " ".join(options.services)
        extra_env["WINTER_LOG_FOLLOW"] = "1" if options.follow else "0"
        extra_env["WINTER_LOG_TAIL"] = str(options.tail)
        extra_env["WINTER_LOG_SINCE"] = options.since_rfc3339
        extra_env["WINTER_LOG_UNTIL"] = options.until_rfc3339
        extra_env["WINTER_LOG_TIMESTAMPS"] = "1" if options.timestamps else "0"

        processor = LogStreamProcessor(options, since_dt, until_dt)

        exit_code = 0
        try:
            with self._subprocess_runner.popen(cmd, env=extra_env, merge_stderr=False) as proc:
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
