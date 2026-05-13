# Worktree Operations

Git commands for the polyrepo workspace topology. All paths are relative to the workspace root.

> **Tip:** For multi-repo setup and bulk operations, prefer `winter ws init` and the other `winter ws` commands over the raw git sequences below — the CLI is idempotent, reads the workspace config, handles pinned repos, and runs in parallel. See [winter-cli/usage.md](./winter-cli/usage.md) for the full command reference. The raw git commands here are still useful for single-repo work and for understanding what the CLI does under the hood.

## Pinned repos

Some repos are **pinned** — they always track the remote main branch and never participate in feature branching. Declare pinning by setting `pinned = true` on a `[[project_repository]]` entry in `workspace:/.winter/config.toml`. The main branch comes from the entry's `main_branch` field, falling back to the workspace-wide `default_main_branch`.

The CLI treats pinned repos specially across commands:

- **init** — sets the worktree branch's upstream to `origin/<main-branch>` and `push.default=upstream`, so `git push` lands on the main branch.
- **connect / disconnect** — skipped; pinned repos never get a feature-branch upstream.
- **sync / pull** — pulled from `origin/<main-branch>` via `--ff-only` (for `pull`, this is the asymmetry from non-pinned, which pull from `origin/<feature-branch>`).
- **push** — excluded by default. Use `--include-pinned` to push pinned worktrees alongside non-pinned, or `--only-pinned` to push just the pinned set. Pushed pinned worktrees go to whatever upstream their local branch tracks (typically `origin/<main>`, but the user can re-target with `git branch --set-upstream-to`).

## Cloning (source checkouts)

```bash
winter ws init
```

This reads `.winter/config.toml`, clones every declared repo that's missing into `projects/`, applies git identity, writes git-exclude entries, and runs each repo's `cmd` list. Safe to re-run.

Raw equivalent for a single repo:

```bash
git clone <repo-url> ./projects/<repo-name>
```

## Creating a feature environment

```bash
winter ws init <name>
```

This command:

- Creates the `./<name>/` directory.
- For each project repo, runs `git worktree add -b <name> <main-branch>`.
- Copies git identity into each worktree.
- Writes git-exclude entries.
- For pinned repos, wires the upstream to `origin/<main-branch>` — see [Pinned repos](#pinned-repos).
- Runs each repo's `cmd` list.
- Seeds `./<name>/.winter.env` with `WINTER_ENV`, `WINTER_ENV_INDEX`, and `WINTER_PORT_BASE`.
- Runs every installed extension's `on_env_init` hook.

Greek letters (`alpha`, `beta`, …) are the convention because they carry a port-offset index, but any valid name works.

After this runs, follow `workspace:/ai/project/project-setup.md` for project-specific orchestration (appending project-specific vars to `.winter.env`, provisioning per-environment resources, generating other env files, anything else the project needs).

Raw equivalent, per repo:

```bash
git -C ./projects/<repo-name> worktree add ../../<name>/<repo-name> -b <name> <main-branch>
```

## Connecting a feature environment to a remote feature branch

```bash
winter ws connect <name> <feature-branch>
```

Sets `push.default=upstream` and the upstream (`origin/<feature-branch>`) on each non-pinned repo's worktree. The connected feature branch is read back from git's upstream tracking on the first non-pinned repo, so all non-pinned repos in an env must use the same remote feature branch name. The remote branch is not created yet — that happens on first push:

```bash
git -C "./<name>/<repo-name>" push -u origin <name>:<feature-branch>
```

**If the recorded feature branch is empty when the user asks to push**, do not guess — ask the user which remote branch they want to push to. Once they provide one, run `winter ws connect` before pushing.

**Before pushing**, ask the user: "Want me to run pre-release checks (lint, format, tests) on the changed repos before pushing?" If they agree, run the checks from the Pre-Release Checklist in [development.md](./project/general/development.md) for each repo with changes. Fix any issues before pushing.

Pinned repos are skipped during connect/disconnect (no feature branch tracking to set/unset) and excluded from `push` by default. See the [Pinned repos](#pinned-repos) section for how to include them.

## Disconnecting a feature environment

```bash
winter ws disconnect <name>
```

Unsets upstream tracking on each non-pinned repo. With no upstream set, the env reads as disconnected.

## Syncing a feature environment against main

```bash
winter ws sync <name>
```

Fetches every repo in parallel, tries `git merge --ff-only origin/<main-branch>` on each worktree (falls back to a 3-way merge if ff-only fails), then fast-forwards the source checkout in `projects/`. Pinned repos are reset to `origin/<main-branch>` via the same ff-only path. Main branch per repo is read from the config — `main_branch` on the `[[project_repository]]` entry if set, otherwise the top-level `main_branch`.

## Pulling remote feature-branch commits

```bash
winter ws pull <name>                # ff-only (default) — diverged repos reported, not touched
winter ws pull <name> --merge        # fall back to a 3-way merge commit
winter ws pull <name> --rebase       # replay local commits onto upstream
winter ws pull <name> --autostash    # stash dirty tree, integrate, then restore
```

Each repo pulls from its own tracked upstream: non-pinned worktrees from `origin/<feature-branch>` (set by `connect`), pinned worktrees from `origin/<main-branch>`. Standalone repos can be reached with `winter ws pull --standalone` or `winter ws pull --all`.

`pull` is **ff-only by default** — no silent merge commits, no surprise rewrites. Diverged repos are surfaced in the report and the working tree is left untouched. Use `--merge` or `--rebase` to integrate explicitly, or resolve with raw git in the affected repo.

## Pushing completed work

```bash
winter ws push                          # every env's non-pinned worktrees
winter ws push <name>                   # <name>'s non-pinned worktrees (== '<name>/*')
winter ws push <name>/<repo>            # one specific worktree
winter ws push '*/<repo>'               # every env's <repo> worktree
winter ws push 'alpha/*' 'beta/*'       # multiple envs in one shot
winter ws push --include-pinned         # add pinned worktrees to the push set
winter ws push --only-pinned            # push only pinned worktrees
winter ws push --standalone             # standalone repos only (patterns not accepted)
winter ws push --all                    # non-pinned worktrees + standalone
```

`PATTERNS` are segment-aware globs over `<env>/<repo>`. `*` matches within a segment (does not cross `/`); `?` matches one char. A bare env name expands to `<env>/*`. Quote patterns in your shell.

Non-pinned worktrees push to the feature branch recorded during `winter ws connect` (`HEAD:refs/heads/<feature-branch>`, upstream set on first push). Pinned worktrees (when included) and standalone repos plain-push to whatever their local branch tracks. Only repos with commits ahead of upstream are pushed.

If an env has non-pinned repos matched by your patterns but isn't connected, those repos are skipped with an error in the report. Pinned repos matched in the same env still push because they don't need a feature branch.

To push a single standalone repo, use raw git — patterns don't apply to standalone repos.
