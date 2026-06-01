from __future__ import annotations

from winter_cli.config.models import SingletonRepository, SingletonType, WorkspaceConfig
from winter_cli.modules.workspace.repository_factory import RepositoryFactory


def test_get_workspace_repo_returns_workspace_root_singleton(
    workspace_config: WorkspaceConfig,
) -> None:
    """get_workspace_repo() resolves the workspace singleton to the workspace root."""
    factory = RepositoryFactory(workspace_config)

    workspace_repo = factory.get_workspace_repo()

    assert workspace_repo is not None
    assert workspace_repo.name == workspace_config.workspace_root.name
    assert workspace_repo.path == workspace_config.workspace_root


def test_get_workspace_repo_none_without_workspace_singleton(
    workspace_config: WorkspaceConfig,
) -> None:
    """When no workspace singleton is configured, get_workspace_repo() returns None.

    The workspace singleton is normally always present, but the accessor must not
    assume it — other singletons (product/harness) alone yield None.
    """
    config = workspace_config.model_copy(
        update={"singleton_repos": [SingletonRepository(name="product", type=SingletonType.product)]},
    )
    factory = RepositoryFactory(config)

    assert factory.get_workspace_repo() is None
