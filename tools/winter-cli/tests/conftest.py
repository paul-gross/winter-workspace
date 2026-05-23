from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from winter_cli.config.models import (
    AdoptExtensions,
    ProjectRepositoryConfig,
    SingletonRepository,
    SingletonType,
    WorkspaceConfig,
)
from winter_cli.container import Container


@pytest.fixture
def tmp_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Materialize a minimal `.winter/` workspace at tmp_path and chdir into it.

    `WorkspaceConfigService.load()` walks up from cwd looking for a `.winter/`
    directory — chdir-ing into the tmp root lets the real loader run against
    a controlled config without touching the developer's workspace.
    """
    winter_dir = tmp_path / ".winter"
    winter_dir.mkdir()
    (winter_dir / "config.toml").write_text(
        dedent(
            """
            main_branch = "main"
            session_prefix = "test"

            [[project_repository]]
            name = "demo-repo"
            url = "git@example.com:demo/demo-repo.git"
            """
        ).strip()
        + "\n"
    )
    (tmp_path / "projects").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def container(tmp_workspace_root: Path) -> Container:
    """A real DI Container resolved against the tmp workspace.

    Every provider is wired against the tmp_workspace_root config, so resolving
    a service through this fixture exercises the full DI graph — that's the
    end-to-end DI smoke test the issue calls for. Individual service tests can
    still construct collaborators directly when they want tighter control.
    """
    return Container()


@pytest.fixture
def workspace_config(tmp_workspace_root: Path) -> WorkspaceConfig:
    """A hand-rolled WorkspaceConfig anchored at tmp_workspace_root.

    Used by tests that want to construct services directly without going
    through the Container — keeps the config schema explicit in the test.
    """
    return WorkspaceConfig(
        workspace_root=tmp_workspace_root,
        session_prefix="test",
        main_branch="main",
        git_excludes=[],
        git_identity=None,
        adopt_extensions=AdoptExtensions.winter,
        singleton_repos=[SingletonRepository(name=tmp_workspace_root.name, type=SingletonType.workspace)],
        project_repos=[
            ProjectRepositoryConfig(name="demo-repo", url="git@example.com:demo/demo-repo.git"),
        ],
        standalone_repos=[],
    )


@pytest.fixture
def init_reporter() -> FakeInitReporter:
    return FakeInitReporter()


class FakeInitReporter:
    """In-memory reporter that records every IInitReporter event for assertion.

    Used in lieu of a mock so tests can assert against the action vocabulary
    (e.g. `("cloned", "demo-repo")`) without coupling to call ordering.
    """

    def __init__(self) -> None:
        self.targets_started: list[str] = []
        self.targets_completed: list[tuple[str, bool]] = []
        self.actions: list[tuple[str, str, str, str]] = []
        self.errors: list[tuple[str, str]] = []
        self.cmds_started: list[tuple[str, str]] = []
        self.cmd_output: list[tuple[str, str]] = []
        self.cmds_completed: list[tuple[str, str, int]] = []

    def target_started(self, target: str) -> None:
        self.targets_started.append(target)

    def target_completed(self, target: str, success: bool) -> None:
        self.targets_completed.append((target, success))

    def repo_action(self, repo: str, location: str, action: str, detail: str = "") -> None:
        self.actions.append((repo, location, action, detail))

    def repo_error(self, repo: str, error: str) -> None:
        self.errors.append((repo, error))

    def cmd_started(self, repo: str, command: str) -> None:
        self.cmds_started.append((repo, command))

    def cmd_output_line(self, repo: str, line: str) -> None:
        self.cmd_output.append((repo, line))

    def cmd_completed(self, repo: str, command: str, returncode: int) -> None:
        self.cmds_completed.append((repo, command, returncode))


@pytest.fixture
def click_recorder() -> ClickRecorder:
    """A drop-in for the `click` module — captures echo calls instead of writing."""
    return ClickRecorder()


class ClickRecorder:
    """Records `click.echo(message, err=...)` calls instead of writing them.

    DriftWarningService takes a `click` module via DI so output can be captured
    in tests. This recorder satisfies the `Any` type without dragging the real
    click side effects into the test.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def echo(self, message: str, err: bool = False, **_: Any) -> None:
        self.calls.append((message, err))


def make_git_repo(path: Path, initial_branch: str = "main") -> None:
    """Create a real git repo at `path` with a single commit on `initial_branch`.

    Shared across read/write repository tests so each one doesn't reinvent
    the same bootstrap (init → identity → commit).
    """
    import git

    r = git.Repo.init(str(path), initial_branch=initial_branch)
    with r.config_writer(config_level="repository") as cw:
        cw.set_value("user", "name", "test")
        cw.set_value("user", "email", "test@example.com")
    (path / "README.md").write_text("hello\n")
    r.git.add("README.md")
    r.git.commit("-m", "init")
