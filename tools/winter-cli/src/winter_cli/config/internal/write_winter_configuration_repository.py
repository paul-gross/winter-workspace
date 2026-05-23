from __future__ import annotations

from pathlib import Path

import tomlkit

from winter_cli.config.models import (
    ProjectRepositoryConfig,
    StandaloneRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.config.workspace import CONFIG_FILE, LOCAL_CONFIG_FILE, WINTER_DIR


class WriteWinterConfigurationRepository:
    """Mutates the workspace's winter configuration files via tomlkit, preserving
    comments and surrounding structure.

    Targets `.winter/config.toml` by default; with `local=True`, targets the
    overlay `.winter/config.local.toml` (auto-created on first write).

    Takes Pydantic config models for appends so only fields the caller explicitly
    set land in the file. Removals match by explicit `name` or URL-derived name.
    """

    def __init__(self, workspace_config: WorkspaceConfig) -> None:
        winter_dir = workspace_config.workspace_root / WINTER_DIR
        self._shared_path = winter_dir / CONFIG_FILE
        self._local_path = winter_dir / LOCAL_CONFIG_FILE

    def append_project_repository(self, config: ProjectRepositoryConfig, local: bool = False) -> None:
        self._append_block("project_repository", config.model_dump(exclude_defaults=True, exclude_none=True), local)

    def append_standalone_repository(self, config: StandaloneRepositoryConfig, local: bool = False) -> None:
        self._append_block(
            "standalone_repository",
            config.model_dump(exclude_defaults=True, exclude_none=True),
            local,
        )

    def remove_project_repository(self, name: str, local: bool = False) -> bool:
        return self._remove_block("project_repository", name, local)

    def remove_standalone_repository(self, name: str, local: bool = False) -> bool:
        return self._remove_block("standalone_repository", name, local)

    def _append_block(self, table_name: str, fields: dict, local: bool) -> None:
        path = self._path_for(local)
        doc = self._load(path, allow_missing=local)
        block = tomlkit.table()
        for key, value in fields.items():
            block[key] = value
        if table_name in doc:
            doc[table_name].append(block)
        else:
            aot = tomlkit.aot()
            aot.append(block)
            doc[table_name] = aot
        path.write_text(tomlkit.dumps(doc))

    def _remove_block(self, table_name: str, target_name: str, local: bool) -> bool:
        path = self._path_for(local)
        if local and not path.exists():
            return False
        doc = self._load(path, allow_missing=False)
        aot = doc.get(table_name)
        if aot is None:
            return False
        for index, block in enumerate(aot):
            explicit = block.get("name")
            url = block.get("url")
            effective = str(explicit) if explicit is not None else (self._name_from_url(str(url)) if url else None)
            if effective != target_name:
                continue
            del aot[index]
            path.write_text(tomlkit.dumps(doc))
            return True
        return False

    def _path_for(self, local: bool) -> Path:
        return self._local_path if local else self._shared_path

    @staticmethod
    def _load(path: Path, allow_missing: bool) -> tomlkit.TOMLDocument:
        if not path.exists():
            if allow_missing:
                return tomlkit.document()
            raise FileNotFoundError(f"Config file not found: {path}")
        return tomlkit.parse(path.read_text())

    @staticmethod
    def _name_from_url(url: str) -> str:
        stripped = url.rstrip("/")
        cut = max(stripped.rfind("/"), stripped.rfind(":"))
        candidate = stripped[cut + 1 :] if cut != -1 else stripped
        return candidate.removesuffix(".git")
