from __future__ import annotations

import dataclasses

from winter_cli.modules.capability.capability_registry_service import CapabilityRegistryService
from winter_cli.modules.capability.capability_reporter import (
    ICapabilityReporter,
    JsonCapabilityReporter,
    StreamCapabilityReporter,
)


@dataclasses.dataclass
class CapabilitiesParams:
    output_json: bool


class CapabilitiesHandler:
    """Dispatches `winter capabilities` runs: describe all slots, render with the reporter."""

    def __init__(
        self,
        registry: CapabilityRegistryService,
        stream_reporter: StreamCapabilityReporter,
        json_reporter: JsonCapabilityReporter,
    ) -> None:
        self._registry = registry
        self._stream_reporter = stream_reporter
        self._json_reporter = json_reporter

    def run(self, params: CapabilitiesParams) -> None:
        resolutions = self._registry.describe_all()
        reporter: ICapabilityReporter = self._json_reporter if params.output_json else self._stream_reporter
        reporter.render(resolutions)
