from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from winter_cli.container import Container


@dataclass(frozen=True)
class CliContext:
    container: Container
    source_override: str | None = None


def cli_ctx(ctx: click.Context) -> CliContext:
    return ctx.obj
