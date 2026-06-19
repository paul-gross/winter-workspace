"""Captures and renders the orchestrator's structured status document.

The orchestrator is invoked as ``<entrypoint> status [pattern...]`` with stdout
piped.  Winter parses the captured stdout as a ``StatusDocument``, applies the
backstop filter, then either re-serialises to canonical JSON (``--json``) or
renders a human table.  The orchestrator argv is byte-identical whether or not
``--json`` is set — ``--json`` is never sent to the orchestrator.

Returns the orchestrator's exit code, or 130 on KeyboardInterrupt.  When the
orchestrator's stdout cannot be parsed as a conformant status document a clear
actionable message is written to stderr and the exit code is the orchestrator's
own non-zero code (or 1 if the orchestrator exited 0).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from winter_cli.core.cli_output_service import Cell, ICliOutputService
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.service.orchestrator_resolver import ServiceOrchestratorResolver
from winter_cli.modules.service.status_filter import filter_status
from winter_cli.modules.service.status_models import StatusDocument, StatusOptions
from winter_cli.modules.service.status_parser import StatusDocumentParser, StatusParseError

_STATE_STYLE: dict[str, str] = {
    "running": "green",
    "stopped": "red",
    "unknown": "dim",
}
_HEALTH_STYLE: dict[str, str] = {
    "healthy": "green",
    "unhealthy": "red",
    "unknown": "dim",
}


class ServiceStatusService:
    """Captures and renders the orchestrator's structured status document.

    Invokes the orchestrator entrypoint as ``<entrypoint> status <pattern...>``
    with cwd at the workspace root.  Patterns are forwarded verbatim as
    positional argv tokens.  The three context vars ``WINTER_WORKSPACE_DIR``,
    ``WINTER_EXT_DIR``, and ``WINTER_EXT_PREFIX`` are exported; no status-specific
    env vars are added.  The orchestrator's stderr inherits the parent's fd so
    diagnostics reach the terminal without corrupting the JSON stream.

    Returns the orchestrator's exit code, or 130 if interrupted by KeyboardInterrupt.
    ``status_parser`` is injected to parse and serialise the orchestrator's JSON output.
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        orchestrator_resolver: ServiceOrchestratorResolver,
        status_parser: StatusDocumentParser,
        cli_output: ICliOutputService,
        click: Any,
        workspace_root: Path,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._orchestrator_resolver = orchestrator_resolver
        self._status_parser = status_parser
        self._cli_output = cli_output
        self._click = click
        self._workspace_root = workspace_root

    def report(self, options: StatusOptions) -> int:
        """Run the orchestrator status entrypoint and render the result."""
        resolved = self._orchestrator_resolver.resolve()
        cmd = [str(resolved.entrypoint), "status", *options.patterns]

        merged = os.environ.copy()
        merged["WINTER_WORKSPACE_DIR"] = str(self._workspace_root)
        merged["WINTER_EXT_DIR"] = str(resolved.ext_dir)
        merged["WINTER_EXT_PREFIX"] = resolved.prefix

        exit_code = 0
        lines: list[str] = []
        try:
            with self._subprocess_runner.popen(cmd, cwd=self._workspace_root, env=merged, merge_stderr=False) as proc:
                try:
                    for line in proc.stdout_lines:
                        lines.append(line)
                except KeyboardInterrupt:
                    return 130

                exit_code = proc.wait()
        except KeyboardInterrupt:
            return 130

        raw = "\n".join(lines)
        try:
            doc: StatusDocument = self._status_parser.parse(raw)
        except StatusParseError as exc:
            self._click.echo(
                f"error: orchestrator at {resolved.entrypoint} (prefix: {resolved.prefix!r}) "
                f"does not emit the structured status document required by the `winter service` contract "
                f"— ensure the extension is up to date. "
                f"Schema: ai/winter-cli/usage/service.md#status-wire-contract\n"
                f"Parse detail: {exc}",
                err=True,
            )
            return exit_code or 1

        doc = filter_status(doc, options.patterns)

        if options.as_json:
            self._click.echo(json.dumps(self._status_parser.to_json_obj(doc), indent=2))
            return exit_code

        self._render_human(doc)
        return exit_code

    def _render_human(self, doc: StatusDocument) -> None:
        """Render a grouped, styled human-readable status table."""
        if not doc.envs:
            self._click.echo("no services")
            return

        headers = ["SERVICE", "STATE", "HEALTH", "PORTS", "SINCE", "HANDLE"]
        first = True
        for env in doc.envs:
            if not first:
                self._click.echo("")
            first = False

            session_str = env.session if env.session is not None else "-"
            port_base_str = str(env.port_base) if env.port_base is not None else "-"
            header_text = f"{env.env}  session={session_str}  port_base={port_base_str}"
            self._click.echo(self._cli_output.style(header_text, "bold"))

            rows: list[list[str | Cell]] = []
            for svc in env.services:
                ports_str = ", ".join(str(p) for p in svc.ports) if svc.ports else "-"
                state_cell = Cell.of(svc.state, _STATE_STYLE.get(svc.state, "dim"))
                health_cell = Cell.of(svc.health, _HEALTH_STYLE.get(svc.health, "dim"))
                rows.append(
                    [
                        svc.name,
                        state_cell,
                        health_cell,
                        ports_str,
                        svc.since or "-",
                        svc.handle or "-",
                    ]
                )

            for line in self._cli_output.render_table(rows, headers=headers):
                self._click.echo(line)
