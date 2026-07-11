from __future__ import annotations

from typing import Protocol

from winter_cli.modules.workspace.models import (
    FeatureEnvironment,
    FeatureEnvironmentStatus,
    ProjectRepository,
    Workspace,
)


class IReadWorkspaceRepository(Protocol):
    def get_environments(
        self, workspace: Workspace, project_repos: list[ProjectRepository]
    ) -> list[FeatureEnvironment]: ...
    def get_environment(self, workspace: Workspace, name: str) -> FeatureEnvironment: ...
    def get_environment_status(
        self,
        env: FeatureEnvironment,
        project_repos: list[ProjectRepository],
        worktree_tracking: dict[str, str | None] | None = None,
    ) -> FeatureEnvironmentStatus: ...
