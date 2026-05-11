from __future__ import annotations

import click

from winter_cli.cli_context import cli_ctx


@click.command()
@click.pass_context
def dashboard(ctx: click.Context):
    """Launch the TUI dashboard."""
    from winter_cli.modules.tui.app import WinterDashboardApp

    context = cli_ctx(ctx)
    app = WinterDashboardApp(context.container, source_override=context.source_override)
    app.run()
