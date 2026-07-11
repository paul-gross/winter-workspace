from __future__ import annotations

from pathlib import Path

import git

from winter_cli.modules.workspace.internal.repo_error_factory import RepoErrorFactory


def read_origin_merge_branch(
    r: git.Repo,
    error_factory: RepoErrorFactory,
    *,
    cwd: Path,
    label: str,
) -> str | None:
    """The bare branch the open repo's HEAD tracks on `origin`, or None.

    Returns the branch name from `branch.<head>.merge` (e.g. `feature/x`, with
    any embedded slashes preserved) when `branch.<head>.remote` is `origin`,
    and None when HEAD is detached/unborn or no `origin` upstream is configured.

    Reads `branch.<head>.{remote,merge}` directly rather than via `@{upstream}`
    / `tracking_branch()`: those resolve to None until the remote-tracking ref
    exists locally, which it won't for a freshly connected feature branch that
    has never been pushed or fetched — exactly the first-push case `ws push`
    must still resolve a target for, and the "connected immediately" read
    `ws status` needs. This is the single source for that read; both the
    push-target resolver (`WriteRepoRepository.get_worktree_push_branch`) and
    the per-worktree feature-branch read (`ReadWorkspaceRepository._read_worktree_feature_branch`)
    call it. No network.
    """
    # TypeError on detached HEAD, ValueError on unborn HEAD: both mean
    # "no tracked branch yet", not a failure.
    try:
        head = r.active_branch.name
    except (TypeError, ValueError):
        return None
    # `git config --get` exits 1 specifically for "key not set" — the
    # "no upstream" answer. Any other exit code is a real failure.
    try:
        remote = r.git.config("--get", f"branch.{head}.remote").strip()
        merge = r.git.config("--get", f"branch.{head}.merge").strip()
    except git.GitCommandError as exc:
        if exc.status == 1:
            return None  # branch.<head>.{remote,merge} not configured
        raise error_factory.from_git(
            exc,
            message=f"reading branch tracking config failed for {label}",
            cwd=cwd,
        ) from exc
    if remote != "origin" or not merge.startswith("refs/heads/"):
        return None
    return merge[len("refs/heads/") :]


def feature_branch_from_upstream(tracking_branch: str | None) -> str | None:
    """Derive the bare origin-tracked branch name from a porcelain `branch.upstream` value.

    `tracking_branch` is `<remote>/<upstream-branch-short-name>` — the porcelain-v2
    `# branch.upstream` header value already read by `_parse_status_porcelain_v2`
    as part of the status piece's single porcelain call, present the moment the
    upstream is configured (no fetch required, same "connected immediately"
    contract `read_origin_merge_branch` provides). Splitting on the first `/`
    isolates the remote name (git remote names cannot contain `/`) from the
    branch, which may itself contain further slashes (e.g. `feature/x`).

    Mirrors `read_origin_merge_branch`'s "origin only" contract: any other
    remote, or no upstream at all, returns `None`. Callers that already hold a
    `RepoStatus.tracking_branch` from the same gathering exercise use this
    instead of opening a second `git.Repo` just to re-read the same config via
    `branch.<head>.{remote,merge}`.
    """
    if tracking_branch is None:
        return None
    remote, sep, branch = tracking_branch.partition("/")
    if not sep or remote != "origin":
        return None
    return branch
