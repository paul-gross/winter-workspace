from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import git
import pytest

from winter_cli.modules.workspace.internal import gitpython_repository
from winter_cli.modules.workspace.internal.gitpython_repository import GitPythonRepository
from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory
from winter_cli.modules.workspace.models import RepoError
from winter_cli.modules.workspace.models.domain_model import RefKind

_REPO_PATH = Path("/fake/repo")
_SOURCE_PATH = Path("/fake/source")
_WT_PATH = Path("/fake/alpha/repo")
_DEST_PATH = Path("/fake/dest")


def _fake_git_repo(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    git_mock = MagicMock()
    # Keep real exception classes so the adapter's except clauses resolve correctly.
    git_mock.GitCommandError = git.GitCommandError
    git_mock.InvalidGitRepositoryError = git.InvalidGitRepositoryError
    git_mock.NoSuchPathError = git.NoSuchPathError
    # The implementation uses `with git.Repo(...) as r:`, so __enter__ must return
    # the same mock that tests assert against.
    git_mock.Repo.return_value.__enter__.return_value = git_mock.Repo.return_value
    monkeypatch.setattr(gitpython_repository, "git", git_mock)
    return git_mock


@pytest.fixture
def adapter() -> GitPythonRepository:
    return GitPythonRepository(RepoErrorFactory())


# ── clone ──────────────────────────────────────────────────────────────────


def test_clone_calls_clone_from_with_url_and_dest(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.clone("git@example.com:org/repo.git", _DEST_PATH)

    git_mock.Repo.clone_from.assert_called_once_with("git@example.com:org/repo.git", str(_DEST_PATH))


def test_clone_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.clone_from.side_effect = git.GitCommandError(("git", "clone", "origin"), 128, stderr=b"not found")

    with pytest.raises(RepoError) as ei:
        adapter.clone("git@example.com:org/repo.git", _DEST_PATH)

    assert "clone failed" in ei.value.message
    assert ei.value.subcommand == "clone"


# ── add_worktree ───────────────────────────────────────────────────────────


def test_add_worktree_without_base_branch_calls_worktree_add(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.add_worktree(_SOURCE_PATH, _WT_PATH, branch="alpha")

    git_mock.Repo.assert_called_once_with(str(_SOURCE_PATH))
    git_mock.Repo.return_value.git.worktree.assert_called_once_with("add", str(_WT_PATH), "alpha")


def test_add_worktree_with_base_branch_passes_b_flag(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.add_worktree(_SOURCE_PATH, _WT_PATH, branch="alpha", base_branch="main")

    git_mock.Repo.return_value.git.worktree.assert_called_once_with(
        "add", str(_WT_PATH), "-b", "alpha", "--no-track", "main"
    )


def test_add_worktree_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.worktree.side_effect = git.GitCommandError(
        ("git", "worktree", "add"), 128, stderr=b"already exists"
    )

    with pytest.raises(RepoError) as ei:
        adapter.add_worktree(_SOURCE_PATH, _WT_PATH, branch="alpha")

    assert "worktree add failed" in ei.value.message
    assert ei.value.subcommand == "worktree"


# ── remove_worktree ────────────────────────────────────────────────────────


def test_remove_worktree_without_force_calls_remove(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.remove_worktree(_SOURCE_PATH, _WT_PATH, force=False)

    git_mock.Repo.return_value.git.worktree.assert_called_once_with("remove", str(_WT_PATH))


def test_remove_worktree_with_force_passes_force_flag(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.remove_worktree(_SOURCE_PATH, _WT_PATH, force=True)

    git_mock.Repo.return_value.git.worktree.assert_called_once_with("remove", "--force", str(_WT_PATH))


def test_remove_worktree_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.worktree.side_effect = git.GitCommandError(
        ("git", "worktree", "remove"), 128, stderr=b"dirty"
    )

    with pytest.raises(RepoError) as ei:
        adapter.remove_worktree(_SOURCE_PATH, _WT_PATH, force=False)

    assert "worktree remove failed" in ei.value.message


# ── list_worktrees ─────────────────────────────────────────────────────────


def test_list_worktrees_parses_porcelain_output(monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.worktree.return_value = (
        "worktree /repo/main\nHEAD abc123\nbranch refs/heads/main\n\n"
        "worktree /repo/alpha\nHEAD def456\nbranch refs/heads/alpha\n"
    )

    result = adapter.list_worktrees(_SOURCE_PATH)

    assert result == [Path("/repo/main"), Path("/repo/alpha")]
    git_mock.Repo.return_value.git.worktree.assert_called_once_with("list", "--porcelain")


def test_list_worktrees_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.worktree.side_effect = git.GitCommandError(
        ("git", "worktree", "list"), 128, stderr=b"not a git repo"
    )

    with pytest.raises(RepoError) as ei:
        adapter.list_worktrees(_SOURCE_PATH)

    assert "worktree list failed" in ei.value.message


# ── get_local_branches ─────────────────────────────────────────────────────


def test_get_local_branches_returns_head_names(monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    head_a = MagicMock()
    head_a.name = "main"
    head_b = MagicMock()
    head_b.name = "alpha"
    git_mock.Repo.return_value.heads = [head_a, head_b]

    result = adapter.get_local_branches(_REPO_PATH)

    assert result == ["main", "alpha"]


def test_get_local_branches_returns_empty_for_no_heads(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.heads = []

    result = adapter.get_local_branches(_REPO_PATH)

    assert result == []


# ── get_tracking_branch ────────────────────────────────────────────────────


def test_get_tracking_branch_returns_name_when_set(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    tb = MagicMock()
    tb.name = "origin/main"
    git_mock.Repo.return_value.active_branch.tracking_branch.return_value = tb

    result = adapter.get_tracking_branch(_REPO_PATH)

    assert result == "origin/main"


def test_get_tracking_branch_returns_none_when_not_set(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.active_branch.tracking_branch.return_value = None

    result = adapter.get_tracking_branch(_REPO_PATH)

    assert result is None


def test_get_tracking_branch_returns_none_on_type_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.active_branch.tracking_branch.side_effect = TypeError("detached HEAD")

    result = adapter.get_tracking_branch(_REPO_PATH)

    assert result is None


# ── set_upstream_to ────────────────────────────────────────────────────────


def test_set_upstream_to_calls_branch_set_upstream(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.set_upstream_to(_REPO_PATH, "origin/main")

    git_mock.Repo.return_value.git.branch.assert_called_once_with("--set-upstream-to", "origin/main")


def test_set_upstream_to_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.branch.side_effect = git.GitCommandError(
        ("git", "branch", "--set-upstream-to"), 128, stderr=b"no such ref"
    )

    with pytest.raises(RepoError) as ei:
        adapter.set_upstream_to(_REPO_PATH, "origin/nonexistent")

    assert "set-upstream-to" in ei.value.message


# ── set_push_default_upstream ──────────────────────────────────────────────


def test_set_push_default_upstream_writes_config(monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    cw = MagicMock()
    git_mock.Repo.return_value.config_writer.return_value.__enter__ = MagicMock(return_value=cw)
    git_mock.Repo.return_value.config_writer.return_value.__exit__ = MagicMock(return_value=False)

    adapter.set_push_default_upstream(_REPO_PATH)

    cw.set_value.assert_called_once_with("push", "default", "upstream")


# ── set_user_identity ──────────────────────────────────────────────────────


def test_set_user_identity_writes_name_and_email(monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    cw = MagicMock()
    git_mock.Repo.return_value.config_writer.return_value.__enter__ = MagicMock(return_value=cw)
    git_mock.Repo.return_value.config_writer.return_value.__exit__ = MagicMock(return_value=False)

    adapter.set_user_identity(_REPO_PATH, name="Alice", email="alice@example.com")

    git_mock.Repo.assert_called_once_with(str(_REPO_PATH))
    assert call("user", "name", "Alice") in cw.set_value.call_args_list
    assert call("user", "email", "alice@example.com") in cw.set_value.call_args_list


# ── get_push_default ───────────────────────────────────────────────────────


def test_get_push_default_returns_value_when_set(monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    cr = MagicMock()
    cr.get_value.return_value = "upstream"
    git_mock.Repo.return_value.config_reader.return_value.__enter__ = MagicMock(return_value=cr)
    git_mock.Repo.return_value.config_reader.return_value.__exit__ = MagicMock(return_value=False)

    result = adapter.get_push_default(_REPO_PATH)

    assert result == "upstream"
    # Must use config_reader (no lock), not config_writer.
    git_mock.Repo.return_value.config_reader.assert_called_once()
    git_mock.Repo.return_value.config_writer.assert_not_called()


def test_get_push_default_returns_none_when_empty(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    cr = MagicMock()
    cr.get_value.return_value = ""
    git_mock.Repo.return_value.config_reader.return_value.__enter__ = MagicMock(return_value=cr)
    git_mock.Repo.return_value.config_reader.return_value.__exit__ = MagicMock(return_value=False)

    result = adapter.get_push_default(_REPO_PATH)

    assert result is None


# ── is_worktree_clean ──────────────────────────────────────────────────────


def test_is_worktree_clean_returns_true_when_status_empty(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.status.return_value = ""

    result = adapter.is_worktree_clean(_REPO_PATH)

    assert result is True
    git_mock.Repo.return_value.git.status.assert_called_once_with("--porcelain")


def test_is_worktree_clean_returns_false_when_status_nonempty(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.status.return_value = " M README.md\n"

    result = adapter.is_worktree_clean(_REPO_PATH)

    assert result is False


def test_is_worktree_clean_returns_false_on_invalid_git_repository(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.side_effect = git.InvalidGitRepositoryError("not a git repo")

    result = adapter.is_worktree_clean(_REPO_PATH)

    assert result is False


def test_is_worktree_clean_returns_false_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.status.side_effect = git.GitCommandError(
        ("git", "status"), 128, stderr=b"not a git repo"
    )

    result = adapter.is_worktree_clean(_REPO_PATH)

    assert result is False


# ── resolve_ref ────────────────────────────────────────────────────────────


_FULL_SHA = "9f3c1ab2e4d5c6f7089a1b2c3d4e5f60718293a4"


def test_resolve_ref_branch_matches_remote_tracking_ref(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    # First candidate (refs/remotes/origin/<ref>) succeeds → branch.
    git_mock.Repo.return_value.git.rev_parse.return_value = _FULL_SHA

    kind, sha = adapter.resolve_ref(_REPO_PATH, "main")

    assert kind is RefKind.branch
    assert sha == _FULL_SHA
    git_mock.Repo.return_value.git.rev_parse.assert_called_once_with("--verify", "refs/remotes/origin/main")


def test_resolve_ref_tag_matches_on_second_candidate(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    # First candidate fails (not a remote branch), second (tag) succeeds.
    git_mock.Repo.return_value.git.rev_parse.side_effect = [
        git.GitCommandError(("git", "rev-parse", "--verify"), 128),
        _FULL_SHA,
    ]

    kind, sha = adapter.resolve_ref(_REPO_PATH, "v1.4.2")

    assert kind is RefKind.tag
    assert sha == _FULL_SHA
    assert git_mock.Repo.return_value.git.rev_parse.call_count == 2
    git_mock.Repo.return_value.git.rev_parse.assert_called_with("--verify", "refs/tags/v1.4.2")


def test_resolve_ref_commit_matches_on_third_candidate(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    # First two candidates fail; third (raw SHA) succeeds.
    git_mock.Repo.return_value.git.rev_parse.side_effect = [
        git.GitCommandError(("git", "rev-parse", "--verify"), 128),
        git.GitCommandError(("git", "rev-parse", "--verify"), 128),
        _FULL_SHA,
    ]

    kind, sha = adapter.resolve_ref(_REPO_PATH, _FULL_SHA[:8])

    assert kind is RefKind.commit
    assert sha == _FULL_SHA
    assert git_mock.Repo.return_value.git.rev_parse.call_count == 3
    git_mock.Repo.return_value.git.rev_parse.assert_called_with("--verify", f"{_FULL_SHA[:8]}^{{commit}}")


def test_resolve_ref_raises_repo_error_when_all_candidates_fail(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.rev_parse.side_effect = git.GitCommandError(("git", "rev-parse", "--verify"), 128)

    with pytest.raises(RepoError) as ei:
        adapter.resolve_ref(_REPO_PATH, "nonexistent-ref")

    assert "unresolvable ref" in ei.value.message
    assert "nonexistent-ref" in ei.value.message
    assert git_mock.Repo.return_value.git.rev_parse.call_count == 3


# ── checkout_detached ──────────────────────────────────────────────────────


def test_checkout_detached_calls_checkout_with_detach_flag(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.checkout_detached(_REPO_PATH, _FULL_SHA)

    git_mock.Repo.return_value.git.checkout.assert_called_once_with("--detach", _FULL_SHA)


def test_checkout_detached_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.checkout.side_effect = git.GitCommandError(
        ("git", "checkout", "--detach"), 128, stderr=b"no such commit"
    )

    with pytest.raises(RepoError) as ei:
        adapter.checkout_detached(_REPO_PATH, "deadbeef")

    assert "checkout --detach" in ei.value.message
    assert ei.value.subcommand == "checkout"


# ── checkout_branch ────────────────────────────────────────────────────────


def test_checkout_branch_calls_checkout_with_track_flag(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)

    adapter.checkout_branch(_REPO_PATH, "feature")

    git_mock.Repo.return_value.git.checkout.assert_called_once_with("-B", "feature", "--track", "origin/feature")


def test_checkout_branch_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.checkout.side_effect = git.GitCommandError(
        ("git", "checkout", "-B"), 128, stderr=b"no such remote branch"
    )

    with pytest.raises(RepoError) as ei:
        adapter.checkout_branch(_REPO_PATH, "no-such-branch")

    assert "checkout -B" in ei.value.message
    assert ei.value.subcommand == "checkout"


# ── get_head_commit ────────────────────────────────────────────────────────


def test_get_head_commit_returns_full_sha(monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.rev_parse.return_value = _FULL_SHA

    result = adapter.get_head_commit(_REPO_PATH)

    assert result == _FULL_SHA
    git_mock.Repo.return_value.git.rev_parse.assert_called_once_with("HEAD")


def test_get_head_commit_strips_trailing_whitespace(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.rev_parse.return_value = _FULL_SHA + "\n"

    result = adapter.get_head_commit(_REPO_PATH)

    assert result == _FULL_SHA


def test_get_head_commit_raises_repo_error_on_git_command_error(
    monkeypatch: pytest.MonkeyPatch, adapter: GitPythonRepository
) -> None:
    git_mock = _fake_git_repo(monkeypatch)
    git_mock.Repo.return_value.git.rev_parse.side_effect = git.GitCommandError(
        ("git", "rev-parse", "HEAD"), 128, stderr=b"not a git repo"
    )

    with pytest.raises(RepoError) as ei:
        adapter.get_head_commit(_REPO_PATH)

    assert "rev-parse HEAD" in ei.value.message
    assert ei.value.subcommand == "rev-parse"


# ── add_worktree (real-git regression: issue #148) ─────────────────────────
#
# These use a real `git init` repo rather than mocks so the `--no-track` fix
# is validated against actual git behavior — the incidental-upstream bug this
# guards against only reproduces under real git's `branch.autoSetupMerge` /
# remote-tracking-base semantics, which a mocked `git.worktree` call can't
# exercise.


def _configure(r: git.Repo) -> git.Repo:
    with r.config_writer() as cw:
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("user", "name", "Test")
        cw.set_value("commit", "gpgsign", "false")
    return r


def test_add_worktree_no_track_survives_auto_setup_merge_always(tmp_path: Path) -> None:
    """Branch created from a local base is not born tracking that base under `autoSetupMerge = always`."""
    adapter = GitPythonRepository(RepoErrorFactory())
    source = tmp_path / "source"
    r = _configure(git.Repo.init(str(source), initial_branch="master"))
    (source / "README").write_text("init\n")
    r.index.add(["README"])
    r.index.commit("init")
    with r.config_writer() as cw:
        cw.set_value("branch", "autoSetupMerge", "always")

    worktree_path = tmp_path / "env" / "source"
    adapter.add_worktree(source, worktree_path, branch="beta", base_branch="master")

    with git.Repo(str(worktree_path)) as wt:
        tb = wt.active_branch.tracking_branch()
    assert tb is None


def test_add_worktree_no_track_survives_remote_tracking_base(tmp_path: Path) -> None:
    """Branch created from a remote-tracking base ref does not inherit that ref as its upstream."""
    adapter = GitPythonRepository(RepoErrorFactory())
    origin_bare = tmp_path / "origin.git"
    seed = _configure(git.Repo.init(str(tmp_path / "seed"), initial_branch="master"))
    (tmp_path / "seed" / "README").write_text("init\n")
    seed.index.add(["README"])
    seed.index.commit("init")
    seed.git.clone("--bare", str(tmp_path / "seed"), str(origin_bare))

    source = tmp_path / "source"
    _configure(git.Repo.clone_from(str(origin_bare), str(source)))

    worktree_path = tmp_path / "env" / "source"
    adapter.add_worktree(source, worktree_path, branch="gamma", base_branch="origin/master")

    with git.Repo(str(worktree_path)) as wt:
        tb = wt.active_branch.tracking_branch()
    assert tb is None
