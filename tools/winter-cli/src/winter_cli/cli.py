from __future__ import annotations

import sys

# Don't write .pyc files. Plugins are loaded via importlib from inside
# standalone extension repos; without this, every winter run scribbles
# __pycache__/ into the extension's source tree.
sys.dont_write_bytecode = True

import click

from winter_cli.cli_context import CliContext
from winter_cli.modules.tui.command import dashboard
from winter_cli.modules.workspace.command import ws_group, repo_group


@click.group()
@click.option("--source-override", default=None, hidden=True)
@click.pass_context
def cli(ctx: click.Context, source_override: str | None):
    """Winter — workspace management CLI."""
    from winter_cli.container import Container

    ctx.obj = CliContext(container=Container(), source_override=source_override)


cli.add_command(dashboard)
cli.add_command(ws_group)
cli.add_command(repo_group)


if __name__ == "__main__":
    cli()
