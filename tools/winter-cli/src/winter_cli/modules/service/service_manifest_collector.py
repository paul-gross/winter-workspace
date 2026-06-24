"""Collects extension-declared service definitions and writes an aggregated manifest.

Called by ``ServiceFanOutService`` (up/down) to build ``WINTER_SERVICE_MANIFEST``
before invoking each provider.  The manifest file is a TOML document listing every
extension-declared service definition (``name``, ``scope``, ``source``, etc.).
Providers that understand the contract merge these defs into their own config;
providers that predate the contract ignore the env var.

Design: this service is a pure data-collection + serialisation layer.  It does
not know about tmux panes or docker images — it only knows about ``ExtServiceDef``.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import click

from winter_cli.core.config_file import ConfigError
from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.modules.service.ext_service_manifest import (
    AggregatedServiceDefs,
    ExtServiceDef,
    ExtServiceManifestParser,
    ServiceDefinitionAggregator,
    write_service_manifest_toml,
)
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import RepoError
from winter_cli.modules.workspace.repository_factory import IStandaloneRepoProvider

logger = logging.getLogger(__name__)

# The env-var name handed to each provider subprocess.
WINTER_SERVICE_MANIFEST_ENV = "WINTER_SERVICE_MANIFEST"

_PARSER = ExtServiceManifestParser()


class ServiceManifestCollectorService:
    """Aggregates extension-declared service definitions and materialises the manifest.

    ``collect`` returns a ``CollectedManifest`` which exposes the aggregated
    ``AggregatedServiceDefs`` and a ``manifest_path`` (a temporary TOML file) if
    any defs were found.  When no defs are declared anywhere the manifest file is
    not written and ``manifest_path`` is ``None`` — providers receive no
    ``WINTER_SERVICE_MANIFEST`` injection.

    Accepts only the domain scalars it needs (``workspace_root``,
    ``workspace_service_defs_raw``) rather than the whole ``WorkspaceConfig``
    (per the dependency-injection convention in
    ``winter-harness:/architecture/dependency-injection.md``).

    Error handling: a malformed ``[[service]]`` block in any source raises
    ``click.ClickException`` (workspace-config errors) or logs a warning and
    skips the extension (extension manifest errors) — mirroring provision's
    behaviour.
    """

    def __init__(
        self,
        workspace_root: Path,
        workspace_service_defs_raw: list,
        manifest_loader: ExtensionManifestLoader,
        repo_factory: IStandaloneRepoProvider,
        fs: IFilesystemReader,
    ) -> None:
        self._workspace_root = workspace_root
        self._workspace_service_defs_raw = workspace_service_defs_raw
        self._manifest_loader = manifest_loader
        self._repo_factory = repo_factory
        self._fs = fs

    def collect(self) -> CollectedManifest:
        """Collect all service definitions and return the aggregated manifest.

        When the result has ``has_defs`` False, no manifest file is written
        (callers do not inject ``WINTER_SERVICE_MANIFEST``).
        """
        workspace_defs = self._collect_workspace_defs()
        ext_def_groups = self._collect_extension_def_groups()

        aggregator = ServiceDefinitionAggregator()
        try:
            aggregated = aggregator.aggregate(workspace_defs, ext_def_groups)
        except ConfigError as exc:
            raise click.ClickException(f"Service definition collision: {exc}") from exc

        if not aggregated.defs:
            return CollectedManifest(aggregated=aggregated, manifest_path=None)

        # Write to a temp file that survives for the lifetime of the process.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".toml",
            prefix="winter_service_manifest_",
            delete=False,
        ) as tf:
            manifest_path = Path(tf.name)
        write_service_manifest_toml(aggregated.defs, manifest_path)
        logger.debug("wrote service manifest to %s (%d defs)", manifest_path, len(aggregated.defs))

        return CollectedManifest(aggregated=aggregated, manifest_path=manifest_path)

    # ── private helpers ────────────────────────────────────────────────────────

    def _collect_workspace_defs(self) -> list[ExtServiceDef]:
        """Parse the workspace-level [[service]] block."""
        try:
            return _PARSER.parse(self._workspace_service_defs_raw or None, source="workspace")
        except ConfigError as exc:
            raise click.ClickException(f"Malformed workspace [[service]] config: {exc}") from exc

    def _collect_extension_def_groups(self) -> list[list[ExtServiceDef]]:
        """Walk every installed extension and collect their [[service]] defs."""
        groups: list[list[ExtServiceDef]] = []
        for repo in self._repo_factory.get_standalone_repos():
            # Use repo.path (the actual on-disk checkout location) rather than
            # workspace_root/repo.name, since extensions may be installed at a
            # custom path (e.g. .winter/ext/service-tmux for winter-service-tmux).
            manifest_path = repo.path / EXT_MANIFEST
            exists = self._fs.is_file(manifest_path)
            if not exists:
                continue
            try:
                manifest = self._manifest_loader.load(repo, manifest_path)
                if manifest.service_defs:
                    groups.append(list(manifest.service_defs))
            except RepoError as exc:
                logger.warning("Skipping extension %r service defs: %s", repo.name, exc)
        return groups


class CollectedManifest:
    """Result of ``ServiceManifestCollectorService.collect()``.

    ``aggregated`` is the full ordered, deduplicated service-def list.
    ``manifest_path`` is the path to the written TOML file (``None`` when
    no defs were found — providers should not receive ``WINTER_SERVICE_MANIFEST``
    in this case).
    """

    def __init__(self, aggregated: AggregatedServiceDefs, manifest_path: Path | None) -> None:
        self.aggregated = aggregated
        self.manifest_path = manifest_path

    @property
    def has_defs(self) -> bool:
        return bool(self.aggregated.defs)

    def env_additions(self) -> dict[str, str]:
        """Return extra env-var overrides to inject into provider subprocess calls.

        Returns ``{WINTER_SERVICE_MANIFEST: "<path>"}`` when a manifest was
        written; returns an empty dict when there are no extension-declared defs.
        """
        if self.manifest_path is None:
            return {}
        return {WINTER_SERVICE_MANIFEST_ENV: str(self.manifest_path)}
