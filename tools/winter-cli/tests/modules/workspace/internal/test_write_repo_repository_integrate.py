"""Real-git tests for the commit counts `sync_ff_only` and `integrate` report.

Mocking GitPython's merge / rebase / rev-list plumbing would just test the
mock; these build actual repos in `tmp_path` so the `+N` counts reflect what
git really moved. `sync_ff_only` needs a real `origin` to fetch from, so it
uses a bare remote plus a source clone; `integrate` resolves its target ref
locally, so a sibling branch stands in for `origin/main`.
"""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from winter_cli.modules.workspace.internal.git_ops_service import GitOpsService
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.internal.write_repo_repository import WriteRepoRepository
from winter_cli.modules.workspace.models import (
    FeatureEnvironment,
    FeatureWorktree,
    ProjectRepository,
    PullMode,
    SyncResult,
    Workspace,
)


@pytest.fixture
def repo_svc() -> WriteRepoRepository:
    error_factory = RepoErrorFactory()
    git_ops = GitOpsService(error_factory, sleep=lambda _: None, jitter=lambda: 0.0)
    return WriteRepoRepository(error_factory=error_factory, git_ops=git_ops)


def _configure(r: git.Repo) -> git.Repo:
    with r.config_writer() as cw:
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("user", "name", "Test")
        cw.set_value("commit", "gpgsign", "false")
    return r


def _working_dir(r: git.Repo) -> Path:
    wtd = r.working_tree_dir
    assert wtd is not None, "test fixture initialized repo without a working tree"
    return Path(str(wtd))


def _commit(r: git.Repo, file_name: str, content: str, message: str) -> str:
    path = _working_dir(r) / file_name
    path.write_text(content)
    r.index.add([file_name])
    return r.index.commit(message).hexsha


def _project(path: Path, name: str = "demo") -> ProjectRepository:
    return ProjectRepository(name=name, main_path=path, main_branch="main")


def _wt(path: Path, name: str = "demo") -> FeatureWorktree:
    workspace = Workspace(root_path=path.parent, session_prefix="t", main_branch="main")
    env = FeatureEnvironment(workspace=workspace, name="alpha", index=1, path=path.parent)
    return FeatureWorktree(workspace=workspace, environment=env, repository=_project(path, name))


# --- sync_ff_only (ws fetch) --------------------------------------------------


def _source_checkout_with_origin(tmp_path: Path) -> tuple[ProjectRepository, git.Repo]:
    """A `src` clone of a bare `origin`, both on an initial `main` commit.

    Returns the source-checkout `ProjectRepository` plus a *second* clone the
    test pushes through to advance `origin/main` out from under `src`.
    """
    seed = _configure(git.Repo.init(str(tmp_path / "seed"), initial_branch="main"))
    _commit(seed, "README", "initial\n", "initial")
    origin = tmp_path / "origin.git"
    seed.git.clone("--bare", str(_working_dir(seed)), str(origin))

    _configure(git.Repo.clone_from(str(origin), str(tmp_path / "src")))  # the source checkout under test
    pusher = _configure(git.Repo.clone_from(str(origin), str(tmp_path / "pusher")))
    return _project(tmp_path / "src"), pusher


def test_sync_ff_only_reports_commits_fast_forwarded(tmp_path: Path, repo_svc: WriteRepoRepository) -> None:
    """A source checkout whose origin/main advanced by 2 reports 2 commits ff'd."""
    project, pusher = _source_checkout_with_origin(tmp_path)
    _commit(pusher, "a.txt", "a\n", "commit a")
    _commit(pusher, "b.txt", "b\n", "commit b")
    pusher.git.push("origin", "main")

    assert repo_svc.sync_ff_only(project) == 2
    assert (project.main_path / "a.txt").exists()


def test_sync_ff_only_reports_zero_when_already_up_to_date(tmp_path: Path, repo_svc: WriteRepoRepository) -> None:
    """No upstream movement ⇒ 0, the signal `ws fetch` renders as `up to date`."""
    project, _pusher = _source_checkout_with_origin(tmp_path)

    assert repo_svc.sync_ff_only(project) == 0


# --- integrate (ws pull) ------------------------------------------------------


def _repo_with_upstream_branch(tmp_path: Path, upstream_commits: int) -> git.Repo:
    """Repo on `main` with an `upstream` sibling branch ahead by N commits.

    `upstream` stands in for `origin/<branch>` — `integrate` resolves the
    target ref locally, so no remote is needed.
    """
    r = _configure(git.Repo.init(str(tmp_path / "demo"), initial_branch="main"))
    _commit(r, "README", "initial\n", "initial")
    r.git.checkout("-b", "upstream")
    for i in range(upstream_commits):
        _commit(r, f"up{i}.txt", f"up{i}\n", f"upstream {i}")
    r.git.checkout("main")
    return r


def test_integrate_ff_only_reports_commits_brought_in(tmp_path: Path, repo_svc: WriteRepoRepository) -> None:
    """Clean fast-forward reports the number of upstream commits integrated."""
    _repo_with_upstream_branch(tmp_path, upstream_commits=3)
    wt = _wt(tmp_path / "demo")

    outcome = repo_svc.integrate(wt, "upstream", PullMode.ff_only, autostash=False)

    assert outcome.sync_result == SyncResult.fast_forwarded
    assert outcome.commits == 3


def test_integrate_up_to_date_reports_zero_commits(tmp_path: Path, repo_svc: WriteRepoRepository) -> None:
    """Nothing to integrate ⇒ up_to_date with commits=0."""
    _repo_with_upstream_branch(tmp_path, upstream_commits=0)
    wt = _wt(tmp_path / "demo")

    outcome = repo_svc.integrate(wt, "upstream", PullMode.ff_only, autostash=False)

    assert outcome.sync_result == SyncResult.up_to_date
    assert outcome.commits == 0


def test_integrate_merge_reports_upstream_commits_brought_in(tmp_path: Path, repo_svc: WriteRepoRepository) -> None:
    """Divergent histories: --merge counts the upstream commits merged in, not the merge commit."""
    r = _repo_with_upstream_branch(tmp_path, upstream_commits=2)
    _commit(r, "local.txt", "local\n", "local work")  # diverge: a local commit ff can't absorb
    wt = _wt(tmp_path / "demo")

    outcome = repo_svc.integrate(wt, "upstream", PullMode.merge, autostash=False)

    assert outcome.sync_result == SyncResult.merged
    assert outcome.commits == 2


def test_integrate_rebase_reports_upstream_commits_brought_in(tmp_path: Path, repo_svc: WriteRepoRepository) -> None:
    """--rebase replays local commits onto upstream and counts the upstream commits brought in."""
    r = _repo_with_upstream_branch(tmp_path, upstream_commits=2)
    _commit(r, "local.txt", "local\n", "local work")
    wt = _wt(tmp_path / "demo")

    outcome = repo_svc.integrate(wt, "upstream", PullMode.rebase, autostash=False)

    assert outcome.sync_result == SyncResult.rebased
    assert outcome.commits == 2
