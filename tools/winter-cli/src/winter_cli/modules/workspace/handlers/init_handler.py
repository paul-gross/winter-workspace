from __future__ import annotations

import dataclasses
import sys

import click

from winter_cli.modules.workspace.init_service import InitService
from winter_cli.modules.workspace.reporter_factory import ReporterFactory


@dataclasses.dataclass
class InitParams:
    target: str | None
    all: bool
    output_json: bool


class InitHandler:
    """Handles `winter ws init` invocations by selecting a reporter and dispatching to the service."""

    def __init__(
        self,
        init_service: InitService,
        reporter_factory: ReporterFactory,
    ) -> None:
        self._init_service = init_service
        self._reporter_factory = reporter_factory

    def run(self, params: InitParams) -> None:
        if params.all and params.target:
            raise click.ClickException("--all cannot be combined with a target name")

        reporter = self._reporter_factory.get_init_reporter(params.output_json)

        if params.all:
            success = self._init_service.reconcile_all(reporter)
        elif params.target:
            success = self._init_service.reconcile_env(params.target, reporter)
        else:
            success = self._init_service.reconcile_projects(reporter)
            if not self._init_service.reconcile_standalones(reporter):
                success = False

        if not success:
            sys.exit(1)
