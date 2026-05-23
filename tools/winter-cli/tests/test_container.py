from __future__ import annotations

from winter_cli.container import Container
from winter_cli.modules.workspace.drift import DriftWarningService
from winter_cli.modules.workspace.init_service import InitService
from winter_cli.modules.workspace.prune_service import PruneService
from winter_cli.modules.workspace.workspace_service import WorkspaceService


def test_container_resolves_workspace_service_end_to_end(container: Container) -> None:
    """DI wiring boots without errors and yields a fully constructed service.

    Resolving `workspace_svc` forces the container to walk the full provider
    graph (workspace_config_svc → workspace_config → repo_repo → workspace →
    repo_factory → worktree_repo → git_ops_svc → workspace_svc). If any
    provider's dependencies drift from the constructor signature, this test
    fails at construction time — long before a CLI invocation would notice.
    """
    svc = container.workspace_svc()
    assert isinstance(svc, WorkspaceService)


def test_container_resolves_every_top_level_service(container: Container) -> None:
    """Smoke-test every singleton/factory service the CLI commands depend on."""
    assert isinstance(container.init_svc(), InitService)
    assert isinstance(container.prune_svc(), PruneService)
    assert isinstance(container.drift_warning_svc(), DriftWarningService)
