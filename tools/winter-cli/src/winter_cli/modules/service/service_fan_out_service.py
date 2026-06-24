"""Fan-out orchestration for `up` and `down` across an ordered provider list.

``ServiceFanOutService`` implements:

- **Forward fan-out (up):** Iterates providers in the order ``resolve_all`` returns
  them (deterministic, for stable output only — no ordering semantics). Runs each
  provider's ``up <env>`` action. Aborts on the first non-zero exit code and returns
  it; subsequent providers are not started.

- **Best-effort fan-out (down):** Iterates providers in the same deterministic order.
  Runs each provider's ``down <env>`` action. Continues past failures; returns the
  first non-zero exit code (0 if all succeeded).

No readiness gate, no status polling, no inter-provider ordering semantics.

Extension-declared service manifests
-------------------------------------
``manifest_collector`` is an optional factory (a ``ServiceManifestCollectorService``
or any callable returning a ``CollectedManifest``).  On ``up``, it is called once and
the resulting ``env_additions()`` dict (``WINTER_SERVICE_MANIFEST=<path>``) is merged
into every provider's subprocess environment.  ``down`` never calls the collector —
it shuts providers down without aggregating manifests.  Providers that understand the
contract read the TOML file and merge the extension-declared services into their live
configuration; providers that predate the contract ignore the env var.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.capability.models import ResolvedCapability
from winter_cli.modules.service.provider_invocation import build_provider_env

if TYPE_CHECKING:
    from winter_cli.modules.service.service_manifest_collector import ServiceManifestCollectorService


class ServiceFanOutService:
    """Orchestrates ``up``/``down`` across an ordered list of providers.

    ``up`` fans out forward, aborting on the first provider failure.
    ``down`` fans out in the same order, best-effort (continues past failures).

    ``manifest_collector`` is an optional ``ServiceManifestCollectorService``
    (or any object with a ``collect()`` method returning a ``CollectedManifest``).
    On ``up``, ``collect()`` is called once and the result's ``env_additions()``
    dict is merged into every provider subprocess env so the provider sees
    ``WINTER_SERVICE_MANIFEST=<path>``.  ``down`` skips collection entirely —
    providers are stopped without manifest aggregation.
    """

    def __init__(
        self,
        subprocess_runner: ISubprocessRunner,
        workspace_root: Path,
        manifest_collector: ServiceManifestCollectorService | None = None,
    ) -> None:
        self._subprocess_runner = subprocess_runner
        self._workspace_root = workspace_root
        self._manifest_collector = manifest_collector

    # ── public interface ──────────────────────────────────────────────────────

    def up(self, env: str, providers: list[ResolvedCapability]) -> int:
        """Start all providers in forward order.

        Collects the extension-declared service manifest once (lazily) and
        injects ``WINTER_SERVICE_MANIFEST`` into every provider subprocess.
        Returns 0 on full success. Returns the first non-zero exit code on
        provider failure, without starting subsequent providers.
        """
        extra_env = self._collect_manifest_env()
        for provider in providers:
            exit_code = self._run_action(provider, "up", [env], extra_env)
            if exit_code != 0:
                return exit_code
        return 0

    def down(self, env: str, providers: list[ResolvedCapability]) -> int:
        """Stop all providers in forward order, best-effort.

        Does NOT collect the service manifest — ``down`` shuts providers down
        without aggregating extension-declared service definitions.
        Continues past failures; returns the first non-zero exit code (or 0 if
        all succeeded).
        """
        first_error: int = 0
        for provider in providers:
            exit_code = self._run_action(provider, "down", [env], {})
            if exit_code != 0 and first_error == 0:
                first_error = exit_code
        return first_error

    # ── internals ────────────────────────────────────────────────────────────

    def _collect_manifest_env(self) -> dict[str, str]:
        """Invoke the manifest collector and return env-var additions for ``up``.

        Returns an empty dict when no collector is configured or when the
        collector finds no extension-declared service definitions.
        """
        if self._manifest_collector is None:
            return {}
        collected = self._manifest_collector.collect()
        return collected.env_additions()

    def _run_action(
        self,
        provider: ResolvedCapability,
        action: str,
        positionals: list[str],
        extra_env: dict[str, str],
    ) -> int:
        cmd = [str(provider.entrypoint), action, *positionals]
        merged = build_provider_env(provider, self._workspace_root)
        if extra_env:
            merged = {**merged, **extra_env}
        return self._subprocess_runner.call(cmd, cwd=self._workspace_root, env=merged)
