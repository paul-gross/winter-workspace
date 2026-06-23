from __future__ import annotations

import dataclasses
import sys

from winter_cli.modules.workspace.destroy_service import DestroyService
from winter_cli.modules.workspace.reporter_factory import ReporterFactory


@dataclasses.dataclass
class DestroyParams:
    env: str
    force: bool
    strict: bool
    dry_run: bool
    output_json: bool
    no_provision_teardown: bool = False


class DestroyHandler:
    """Handles `winter ws destroy` invocations by selecting a reporter and dispatching to the service."""

    def __init__(
        self,
        destroy_service: DestroyService,
        reporter_factory: ReporterFactory,
    ) -> None:
        self._destroy_service = destroy_service
        self._reporter_factory = reporter_factory

    def run(self, params: DestroyParams) -> None:
        reporter = self._reporter_factory.get_init_reporter(params.output_json)
        success = self._destroy_service.destroy_env(
            name=params.env,
            force=params.force,
            strict=params.strict,
            dry_run=params.dry_run,
            reporter=reporter,
            provision_teardown=not params.no_provision_teardown,
        )
        if not success:
            sys.exit(1)
