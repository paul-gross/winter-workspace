from __future__ import annotations

import click

from winter_cli.cli_context import cli_ctx
from winter_cli.modules.capability.handler import CapabilitiesParams


@click.command("capabilities")
@click.option("--json", "output_json", is_flag=True, default=False, help="Emit capability slots as JSON.")
@click.pass_context
def capabilities_command(ctx: click.Context, output_json: bool) -> None:
    """List every known capability slot — its bound provider, other installed candidates,
    and whether each candidate's entrypoint resolves.

    Read-only; always exits 0 even when a slot is ambiguous or misconfigured (the bad
    state is reported, not raised — `winter doctor` is what fails on it).
    """
    container = cli_ctx(ctx).container
    handler = container.capabilities_handler()
    handler.run(CapabilitiesParams(output_json=output_json))
