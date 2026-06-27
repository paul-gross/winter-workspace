"""``winter env`` — print the computed runtime environment for a scope.

Usage::

    winter env <scope>

*scope* is a feature-env name (e.g. ``alpha``) or the reserved literal
``workspace``.  The command prints one ``export KEY=value`` line per
variable in the order the provisioner returns them:

    export WINTER_ENV=alpha
    export WINTER_ENV_INDEX=1
    export WINTER_PORT_BASE=4060
    export WINTER_WORKSPACE_PORT_BASE=4000
    export MY_APP_PORT=4061           # from [env.feature.vars] if declared

The output is designed to be shell-sourced::

    source <(winter env alpha)     # bash/zsh
    . (winter env alpha | psub)    # fish

Exit codes:

- 0 — success.
- 1 — unknown scope (no allocation for the given env name), misconfigured
      env-band template, or other fatal error.
"""

from __future__ import annotations

import shlex

import click

from winter_cli.cli_context import cli_ctx


@click.command("env")
@click.argument("scope")
@click.pass_context
def env_cmd(ctx: click.Context, scope: str) -> None:
    """Print the runtime environment variables for SCOPE as sourceable export lines.

    SCOPE is a feature-env name (e.g. ``alpha``) or ``workspace``.  The output
    can be shell-sourced to inject WINTER_* and env-band variables into the
    current shell session::

        source <(winter env alpha)
    """
    container = cli_ctx(ctx).container
    if scope != "workspace" and scope not in container.env_index_registry().all_assignments():
        click.echo(
            f"winter env: unknown scope {scope!r} — no env by that name is registered",
            err=True,
        )
        ctx.exit(1)
        return
    provisioner = container.env_provisioner()
    try:
        env_map = provisioner.compute(scope)
    except ValueError as exc:
        click.echo(f"winter env: error computing environment for {scope!r}: {exc}", err=True)
        ctx.exit(1)
        return
    for key, value in env_map.items():
        click.echo(f"export {key}={shlex.quote(value)}")
