from __future__ import annotations

from datetime import UTC, datetime

import click

from winter_cli.cli_context import cli_ctx
from winter_cli.modules.service.handler import ServiceParams
from winter_cli.modules.service.models import LogOptions, parse_since_until


@click.group("service")
def service_group() -> None:
    """Control workspace services via the registered orchestrator extension.

    Each action invokes the entrypoint registered in .winter/config.toml as
    `<entrypoint> <action> <env>` (argv). Action-specific parameters are
    conveyed via WINTER_* environment variables so the contract is stable
    across orchestrator implementations.
    """


@service_group.command("up", short_help="Start env services.")
@click.argument("env")
@click.pass_context
def up_cmd(ctx: click.Context, env: str) -> None:
    """Start services for ENV."""
    handler = cli_ctx(ctx).container.service_handler()
    handler.run(ServiceParams(action="up", env=env))


@service_group.command("down", short_help="Stop env services.")
@click.argument("env")
@click.pass_context
def down_cmd(ctx: click.Context, env: str) -> None:
    """Stop services for ENV."""
    handler = cli_ctx(ctx).container.service_handler()
    handler.run(ServiceParams(action="down", env=env))


@service_group.command("status", short_help="Report env service status.")
@click.argument("env")
@click.pass_context
def status_cmd(ctx: click.Context, env: str) -> None:
    """Report service status for ENV."""
    handler = cli_ctx(ctx).container.service_handler()
    handler.run(ServiceParams(action="status", env=env))


@service_group.command("restart", short_help="Bounce one service.")
@click.argument("env")
@click.argument("service")
@click.pass_context
def restart_cmd(ctx: click.Context, env: str, service: str) -> None:
    """Restart SERVICE in ENV.

    The service name is conveyed to the orchestrator via WINTER_SERVICE_NAME.
    """
    handler = cli_ctx(ctx).container.service_handler()
    handler.run(ServiceParams(action="restart", env=env, service_name=service))


def _validate_tail(ctx: click.Context, param: click.Parameter, value: str) -> int | str:
    """Validate --tail: must be a positive integer or the literal 'all'."""
    if value == "all":
        return "all"
    try:
        n = int(value)
    except ValueError:
        raise click.BadParameter("must be a positive integer or 'all'", ctx=ctx, param=param) from None
    if n <= 0:
        raise click.BadParameter("must be a positive integer or 'all'", ctx=ctx, param=param)
    return n


@service_group.command("logs", short_help="Stream service logs.")
@click.argument("env")
@click.argument("service", nargs=-1)
@click.option("-f", "--follow", is_flag=True, default=False, help="Stream until interrupted.")
@click.option(
    "-n",
    "--tail",
    default="200",
    metavar="N",
    callback=_validate_tail,
    is_eager=False,
    help="Last N lines (positive integer or 'all'). Default: 200.",
)
@click.option("--since", default="", metavar="DUR|TS", help="Show logs since duration or RFC3339 timestamp.")
@click.option("--until", default="", metavar="DUR|TS", help="Show logs until duration or RFC3339 timestamp.")
@click.option("-t", "--timestamps", is_flag=True, default=False, help="Prefix each line with its timestamp.")
@click.pass_context
def logs_cmd(
    ctx: click.Context,
    env: str,
    service: tuple[str, ...],
    follow: bool,
    tail: int | str,
    since: str,
    until: str,
    timestamps: bool,
) -> None:
    """Stream logs for ENV.

    SERVICE filters to one or more named services; omit for all services.

    \b
    Duration format: <N>(s|m|h|d) — e.g. 90s, 5m, 2h, 3d.
    Timestamp format: RFC3339 — e.g. 2026-06-13T10:00:00Z.

    Parameters are conveyed to the orchestrator via WINTER_LOG_* environment
    variables. winter applies idempotent backstop filters on the NDJSON output.

    When --follow is set, winter relays lines live and does NOT re-apply tail
    (the orchestrator is expected to honour WINTER_LOG_TAIL). Interrupted with
    Ctrl-C exits 130.
    """
    now = datetime.now(tz=UTC)

    since_rfc3339 = ""
    if since:
        try:
            since_rfc3339 = parse_since_until(since, now)
        except ValueError as exc:
            raise click.BadParameter(str(exc), ctx=ctx, param_hint="'--since'") from exc

    until_rfc3339 = ""
    if until:
        try:
            until_rfc3339 = parse_since_until(until, now)
        except ValueError as exc:
            raise click.BadParameter(str(exc), ctx=ctx, param_hint="'--until'") from exc

    options = LogOptions(
        services=service,
        follow=follow,
        tail=tail,
        since_rfc3339=since_rfc3339,
        until_rfc3339=until_rfc3339,
        timestamps=timestamps,
    )
    handler = cli_ctx(ctx).container.service_handler()
    handler.run_logs(env, options)
