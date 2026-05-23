from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import click

from winter_cli.config.models import ProjectRepositoryConfig, StandaloneRepositoryConfig
from winter_cli.config.winter_configuration_repository import IWriteWinterConfigurationRepository
from winter_cli.core.cli_input_validation_service import ICliInputValidationService
from winter_cli.core.cli_output_service import ICliOutputService
from winter_cli.modules.workspace.drift import DriftWarningService
from winter_cli.modules.workspace.models import (
    ProjectRepository,
    StandaloneRepository,
    Workspace,
)
from winter_cli.modules.workspace.repository_factory import RepositoryFactory


@dataclasses.dataclass
class RepoListParams:
    output_json: bool


@dataclasses.dataclass
class RepoAddParams:
    url: str
    standalone: bool
    name: str | None
    main_branch: str | None
    git_excludes: list[str]
    cmd: list[str]
    pinned: bool
    path: str | None
    prefix: str | None
    local: bool
    output_json: bool


@dataclasses.dataclass
class RepoRemoveParams:
    kind: str
    name: str
    local: bool
    output_json: bool


class RepoHandler:
    def __init__(
        self,
        repo_factory: RepositoryFactory,
        drift_warning_svc: DriftWarningService,
        cli_output_svc: ICliOutputService,
        cli_input_validation_svc: ICliInputValidationService,
        write_winter_config_repo: IWriteWinterConfigurationRepository,
        workspace: Workspace,
    ) -> None:
        self._repo_factory = repo_factory
        self._drift_warning_svc = drift_warning_svc
        self._cli_output_svc = cli_output_svc
        self._cli_input_validation_svc = cli_input_validation_svc
        self._write_winter_config_repo = write_winter_config_repo
        self._workspace = workspace

    def list(self, params: RepoListParams) -> None:
        project_repos = self._repo_factory.get_project_repos()
        standalone_repos = self._repo_factory.get_standalone_repos()
        singleton_repos = [r for r in self._repo_factory.get_singleton_repos() if r.path != self._workspace.root_path]
        self._drift_warning_svc.raise_warning()

        if params.output_json:
            payload = (
                [self._standalone_repo_dict(r, "singleton") for r in singleton_repos]
                + [self._standalone_repo_dict(r, "standalone") for r in standalone_repos]
                + [self._project_repo_dict(r) for r in project_repos]
            )
            click.echo(json.dumps(payload, indent=2))
            return

        rows: list[list[str]] = []
        for r in singleton_repos:
            rows.append([r.url or "-", "singleton", self._relative(r.path)])
        for r in standalone_repos:
            rows.append([r.url or "-", "standalone", self._relative(r.path)])
        for r in project_repos:
            rows.append(
                [
                    r.url or "-",
                    "project",
                    self._relative(r.main_path),
                    "[pinned]" if r.pinned else "",
                ]
            )

        for line in self._cli_output_svc.render_table(rows):
            click.echo(line)

    def add(self, params: RepoAddParams) -> None:
        self._cli_input_validation_svc.validate_git_url(params.url)

        if params.standalone:
            if params.pinned:
                raise click.ClickException("--pinned only applies to project repos")
        else:
            if params.path is not None:
                raise click.ClickException("--path is only valid with --standalone")
            if params.prefix is not None:
                raise click.ClickException("--prefix is only valid with --standalone")

        if params.path is not None:
            candidate = Path(params.path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise click.ClickException(f"--path must be relative and free of '..' segments: {params.path!r}")

        kind = "standalone" if params.standalone else "project"
        new_name = params.name or self._repo_factory.name_from_url(params.url)
        if params.standalone:
            existing = self._repo_factory.get_standalone_repos()
        else:
            existing = self._repo_factory.get_project_repos()
        for r in existing:
            if r.url == params.url:
                raise click.ClickException(f"{kind} repo with url {params.url!r} already declared")
            if r.name == new_name:
                raise click.ClickException(f"{kind} repo with name {new_name!r} already declared")
        if params.standalone:
            new_path = (self._workspace.root_path / (params.path or new_name)).resolve()
            for r in self._repo_factory.get_standalone_repos():
                if r.path.resolve() == new_path:
                    raise click.ClickException(
                        f"standalone repo with path {params.path or new_name!r} already declared"
                    )

        if params.standalone:
            self._write_winter_config_repo.append_standalone_repository(
                StandaloneRepositoryConfig(
                    url=params.url,
                    name=params.name,
                    main_branch=params.main_branch,
                    path=params.path,
                    prefix=params.prefix,
                    git_excludes=params.git_excludes,
                    cmd=params.cmd,
                ),
                local=params.local,
            )
        else:
            self._write_winter_config_repo.append_project_repository(
                ProjectRepositoryConfig(
                    url=params.url,
                    name=params.name,
                    main_branch=params.main_branch,
                    pinned=params.pinned,
                    git_excludes=params.git_excludes,
                    cmd=params.cmd,
                ),
                local=params.local,
            )

        if params.output_json:
            click.echo(
                json.dumps(
                    {
                        "added": True,
                        "kind": kind,
                        "url": params.url,
                    },
                    indent=2,
                )
            )
            return

        click.echo(f"Added {kind} repo: {params.url}")

    def remove(self, params: RepoRemoveParams) -> None:
        if params.kind == "project":
            removed = self._write_winter_config_repo.remove_project_repository(params.name, local=params.local)
        elif params.kind == "standalone":
            removed = self._write_winter_config_repo.remove_standalone_repository(params.name, local=params.local)
        else:
            raise click.ClickException(f"Type must be 'project' or 'standalone', got {params.kind!r}")

        if not removed:
            raise click.ClickException(f"{params.kind} repo {params.name!r} not found")

        if params.output_json:
            click.echo(
                json.dumps(
                    {
                        "removed": True,
                        "kind": params.kind,
                        "name": params.name,
                    },
                    indent=2,
                )
            )
            return

        click.echo(f"Removed {params.kind} repo: {params.name}")

    def _relative(self, p) -> str:
        try:
            return str(p.relative_to(self._workspace.root_path))
        except ValueError:
            return str(p)

    @staticmethod
    def _project_repo_dict(r: ProjectRepository) -> dict:
        return {
            "name": r.name,
            "type": "project",
            "main_path": str(r.main_path),
            "pinned": r.pinned,
        }

    @staticmethod
    def _standalone_repo_dict(r: StandaloneRepository, kind: str) -> dict:
        return {
            "name": r.name,
            "type": kind,
            "path": str(r.path),
        }
