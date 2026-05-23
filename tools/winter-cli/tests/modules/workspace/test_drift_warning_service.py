from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import ClickRecorder
from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    WorkspaceConfig,
)
from winter_cli.modules.workspace.drift import DriftWarningService
from winter_cli.modules.workspace.models import Workspace
from winter_cli.modules.workspace.repository_factory import RepositoryFactory


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(root_path=tmp_path, session_prefix="t", main_branch="main")


@pytest.fixture
def repo_factory(tmp_path: Path) -> RepositoryFactory:
    config = WorkspaceConfig(
        workspace_root=tmp_path,
        session_prefix="t",
        main_branch="main",
        adopt_extensions=AdoptExtensions.winter,
        project_repos=[
            ProjectRepositoryConfig(name="frontend", url="git@example.com:org/frontend.git"),
            ProjectRepositoryConfig(name="backend", url="git@example.com:org/backend.git"),
        ],
    )
    return RepositoryFactory(config)


def _service(
    workspace: Workspace, repo_factory: RepositoryFactory, click_recorder: ClickRecorder
) -> DriftWarningService:
    return DriftWarningService(workspace=workspace, repo_factory=repo_factory, click=click_recorder)


def test_detect_returns_empty_when_projects_dir_missing(
    workspace: Workspace, repo_factory: RepositoryFactory, click_recorder: ClickRecorder
) -> None:
    """No projects/ dir on disk → every declared repo counts as missing."""
    svc = _service(workspace, repo_factory, click_recorder)
    report = svc.detect()
    missing_names = sorted(r.name for r in report.missing)
    assert missing_names == ["backend", "frontend"]
    assert report.undeclared == []


def test_detect_reports_missing_and_undeclared(
    tmp_path: Path, workspace: Workspace, repo_factory: RepositoryFactory, click_recorder: ClickRecorder
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "frontend").mkdir()  # declared and present
    (projects / "stranger").mkdir()  # not declared

    svc = _service(workspace, repo_factory, click_recorder)
    report = svc.detect()

    assert [r.name for r in report.missing] == ["backend"]
    assert report.undeclared == ["stranger"]
    assert report.any is True


def test_raise_warning_echoes_to_stderr_when_drift(
    tmp_path: Path, workspace: Workspace, repo_factory: RepositoryFactory, click_recorder: ClickRecorder
) -> None:
    (tmp_path / "projects").mkdir()
    svc = _service(workspace, repo_factory, click_recorder)

    svc.raise_warning()

    # Single line, marked as stderr, mentioning the missing repos.
    assert len(click_recorder.calls) == 1
    message, err = click_recorder.calls[0]
    assert err is True
    assert "warning:" in message
    assert "backend" in message
    assert "frontend" in message


def test_raise_warning_silent_when_no_drift(
    tmp_path: Path, workspace: Workspace, repo_factory: RepositoryFactory, click_recorder: ClickRecorder
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "frontend").mkdir()
    (projects / "backend").mkdir()
    svc = _service(workspace, repo_factory, click_recorder)

    svc.raise_warning()

    assert click_recorder.calls == []
