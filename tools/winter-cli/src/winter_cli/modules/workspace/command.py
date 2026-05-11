from __future__ import annotations

import click

from winter_cli.cli_context import cli_ctx
from winter_cli.modules.workspace.models import DiffMode
from winter_cli.modules.workspace.handlers import (
    InitParams,
    RepoAddParams,
    RepoListParams,
    RepoRemoveParams,
    WorkspacePruneParams,
    WorktreeConnectParams,
    WorktreeDiffParams,
    WorktreeDisconnectParams,
    WorktreeIndexParams,
    WorktreeListParams,
    WorktreePushParams,
    WorktreeStatusParams,
    WorktreeSyncParams,
)


@click.group("ws")
def ws_group():
    """Manage worktrees."""


@ws_group.command("init")
@click.argument("target", required=False)
@click.option("--all", "all_targets", is_flag=True, default=False, help="Reconcile projects/, standalone repos, and every existing worktree.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_init(ctx: click.Context, target: str | None, all_targets: bool, output_json: bool):
    """Reconcile source checkouts, standalone repos, or a feature worktree against the config.

    \b
      winter ws init              # reconcile projects/ and standalone repos
      winter ws init alpha        # reconcile the alpha/ worktree (create if missing)
      winter ws init --all        # reconcile projects/, standalone repos, and every worktree
    """
    container = cli_ctx(ctx).container
    handler = container.init_handler()
    handler.run(InitParams(target=target, all=all_targets, output_json=output_json))


@ws_group.command("list")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_list(ctx: click.Context, output_json: bool):
    """List all worktrees."""
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.list(WorktreeListParams(output_json=output_json))


@ws_group.command("status")
@click.argument("worktree", required=False)
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_status(ctx: click.Context, worktree: str | None, output_json: bool):
    """Show status for a worktree (defaults to all)."""
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.status(WorktreeStatusParams(worktree=worktree, output_json=output_json))


@ws_group.command("sync")
@click.argument("worktree")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_sync(ctx: click.Context, worktree: str, output_json: bool):
    """Sync a worktree with origin (fetch + ff-only merge)."""
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.sync(WorktreeSyncParams(worktree=worktree, output_json=output_json))


@ws_group.command("connect")
@click.argument("worktree")
@click.argument("feature_branch")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_connect(ctx: click.Context, worktree: str, feature_branch: str, output_json: bool):
    """Connect a worktree to a remote feature branch."""
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.connect(WorktreeConnectParams(worktree=worktree, feature_branch=feature_branch, output_json=output_json))


@ws_group.command("disconnect")
@click.argument("worktree")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_disconnect(ctx: click.Context, worktree: str, output_json: bool):
    """Disconnect a worktree from its feature branch."""
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.disconnect(WorktreeDisconnectParams(worktree=worktree, output_json=output_json))


@ws_group.command("push")
@click.argument("worktree")
@click.argument("repos", nargs=-1)
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_push(ctx: click.Context, worktree: str, repos: tuple[str, ...], output_json: bool):
    """Push worktree repos to their upstream branch."""
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.push(WorktreePushParams(
        worktree=worktree,
        repo_names=list(repos) if repos else None,
        output_json=output_json,
    ))


@ws_group.command("prune")
@click.option("--dry-run", is_flag=True, default=False, help="List what would be removed; don't delete anything.")
@click.option("--force", is_flag=True, default=False, help="Skip confirmation. Still refuses repos with uncommitted work or attached worktrees.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_prune(ctx: click.Context, dry_run: bool, force: bool, output_json: bool):
    """Remove disk state for repos no longer in the workspace config.

    Detects orphan project clones under projects/, orphan standalone clones
    referenced by stale entries in .git/info/exclude, and broken symlinks
    under .claude/skills/ and .claude/agents/. Refuses to delete repos with
    uncommitted changes or attached worktrees.
    """
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.prune(WorkspacePruneParams(dry_run=dry_run, force=force, output_json=output_json))


@ws_group.command("index")
@click.argument("name")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_index(ctx: click.Context, name: str, output_json: bool):
    """Print the port-offset index for a worktree name.

    Greek letters get fixed indices 1..24. Any other name is hashed
    deterministically into 26..281 via SHA-1.
    """
    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.index(WorktreeIndexParams(name=name, output_json=output_json))


@ws_group.command("diff")
@click.argument("worktree")
@click.option("--staged", is_flag=True, help="Show staged changes (index vs HEAD).")
@click.option("--branch", is_flag=True, help="Show full branch diff (HEAD vs main).")
@click.option("--repo", default=None, help="Limit to a single repo.")
@click.option("--no-headers", is_flag=True, help="Omit repo separator headers.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def ws_diff(ctx: click.Context, worktree: str, staged: bool, branch: bool, repo: str | None, no_headers: bool, output_json: bool):
    """Show unified diff across worktree repos."""
    if staged and branch:
        raise click.ClickException("--staged and --branch are mutually exclusive")

    if staged:
        mode = DiffMode.staged
    elif branch:
        mode = DiffMode.branch
    else:
        mode = DiffMode.uncommitted

    container = cli_ctx(ctx).container
    handler = container.workspace_handler()
    handler.diff(WorktreeDiffParams(
        worktree=worktree,
        mode=mode,
        repo_filter=repo,
        no_headers=no_headers,
        output_json=output_json,
    ))


@click.group("repo")
def repo_group():
    """Manage repositories."""


@repo_group.command("list")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def repo_list(ctx: click.Context, output_json: bool):
    """List all repositories."""
    container = cli_ctx(ctx).container
    handler = container.repo_handler()
    handler.list(RepoListParams(output_json=output_json))


@repo_group.command("add")
@click.argument("url")
@click.option("--standalone", is_flag=True, default=False, help="Add as a standalone repository instead of a project repository.")
@click.option("--name", default=None, help="Override URL-derived name.")
@click.option("--main-branch", default=None, help="Per-repo main branch (overrides workspace default).")
@click.option("--git-exclude", "git_excludes", multiple=True, help="Add a .git/info/exclude entry (repeatable).")
@click.option("--cmd", "cmds", multiple=True, help="Post-clone command to run (repeatable).")
@click.option("--pinned", is_flag=True, default=False, help="Pin the repo to its main branch (project only).")
@click.option("--path", default=None, help="Override clone path (standalone only, relative to workspace root).")
@click.option("--prefix", default=None, help="Extension symlink prefix (standalone only).")
@click.option("--local", is_flag=True, default=False, help="Write to config.local.toml instead of the shared config.toml.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def repo_add(
    ctx: click.Context,
    url: str,
    standalone: bool,
    name: str | None,
    main_branch: str | None,
    git_excludes: tuple[str, ...],
    cmds: tuple[str, ...],
    pinned: bool,
    path: str | None,
    prefix: str | None,
    local: bool,
    output_json: bool,
):
    """Add a repository to the workspace config.

    URL may be http(s)://, ssh://, git://, or user@host:path. Defaults to a
    project repository; pass --standalone to add as a standalone instead.
    Writes to .winter/config.toml unless --local is given, in which case the
    entry lands in .winter/config.local.toml (auto-created if missing).
    """
    container = cli_ctx(ctx).container
    handler = container.repo_handler()
    handler.add(RepoAddParams(
        url=url,
        standalone=standalone,
        name=name,
        main_branch=main_branch,
        git_excludes=list(git_excludes),
        cmd=list(cmds),
        pinned=pinned,
        path=path,
        prefix=prefix,
        local=local,
        output_json=output_json,
    ))


@repo_group.command("remove")
@click.argument("target")
@click.option("--local", is_flag=True, default=False, help="Remove from config.local.toml instead of the shared config.toml.")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output as JSON.")
@click.pass_context
def repo_remove(ctx: click.Context, target: str, local: bool, output_json: bool):
    """Remove a repository from the workspace config.

    \b
    TARGET takes the form '<type>/<name>':
      winter repo remove project/winter
      winter repo remove standalone/winter-harness
    """
    if "/" not in target:
        raise click.ClickException(
            "Argument must be in the form '<type>/<name>' "
            "(e.g. project/winter, standalone/winter-harness)"
        )
    kind, _, name = target.partition("/")
    container = cli_ctx(ctx).container
    handler = container.repo_handler()
    handler.remove(RepoRemoveParams(kind=kind, name=name, local=local, output_json=output_json))
