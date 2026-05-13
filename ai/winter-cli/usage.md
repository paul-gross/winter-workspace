# Winter CLI — Usage

Command reference for agents executing `winter` commands. For installation and configuration, see [setup.md](./setup.md).

## When to use the CLI vs raw git

**Use the CLI** for operations that span multiple repos — init, status, sync, connect, push, diff. The CLI handles pinned repos, parallel fetching, source checkout fast-forwarding, and idempotent setup automatically.

**Use raw git** for single-repo operations — staging files, committing, resolving conflicts, interactive rebase, branch inspection. The CLI doesn't replace git for per-repo work.

## `winter ws init` — reconcile the workspace against the config

One idempotent command with three modes. Safe to re-run any time.

| Form | What it reconciles |
|------|--------------------|
| `winter ws init` | Source checkouts in `projects/` and standalone repos. |
| `winter ws init <name>` | The `./<name>/` feature environment. |
| `winter ws init --all` | Source checkouts, standalones, and every existing feature environment. |

Each mode applies the same per-repo reconcile steps (git identity, excludes, `cmd` list, extension processing, pinned-repo tracking on worktrees). See [worktree-ops.md](../worktree-ops.md) for the full step list and the pinned-repo specifics.

Greek letters (`alpha`, `beta`, …) are the suggested convention for feature environment names because they carry a fixed port-offset index 1..24. Any other valid directory name is accepted and gets a deterministic SHA-1-derived index in the range 26..281 (index 25 is reserved as a buffer). Hash collisions among non-Greek names are possible but unlikely.

## Workspace commands (`winter ws`)

| Command | Usage | Purpose |
|---------|-------|---------|
| `winter ws init` | `winter ws init [TARGET] [--all] [--json]` | Reconcile source checkouts or a feature environment |
| `winter ws list` | `winter ws list [--json]` | List all feature environments |
| `winter ws status` | `winter ws status [ENV] [--json]` | Git status across all repos in a feature environment |
| `winter ws sync` | `winter ws sync ENV [--json]` | Fetch all repos, ff-only merge `origin/main` (falls back to merge), then fast-forward source checkouts |
| `winter ws fetch` | `winter ws fetch [PATTERNS...] [--standalone\|--all] [--json]` | Fetch refs from `origin` for project worktrees matched by PATTERNS |
| `winter ws pull` | `winter ws pull [PATTERNS...] [--standalone\|--all] [--ff-only\|--merge\|--rebase] [--autostash] [--json]` | Fetch + ff-only integrate (default) project worktrees matched by PATTERNS |
| `winter ws push` | `winter ws push [PATTERNS...] [--standalone\|--all] [--include-pinned\|--only-pinned] [--json]` | Push project worktrees matched by PATTERNS to their tracked upstream |
| `winter ws connect` | `winter ws connect ENV FEATURE_BRANCH [--json]` | Connect a feature environment to a remote feature branch |
| `winter ws disconnect` | `winter ws disconnect ENV [--json]` | Disconnect a feature environment from its feature branch |
| `winter ws diff` | `winter ws diff ENV [--staged\|--branch] [--repo REPO] [--json]` | Unified diff across all repos in a feature environment |
| `winter ws index` | `winter ws index NAME [--json]` | Print the port-offset index for a feature environment name (Greek = 1..24, other = hashed 26..281) |

### `fetch` / `pull` / `push` patterns and scope

All three commands accept any number of segment-aware glob `PATTERNS` over `<env>/<repo>` (no patterns = `*/*`). A bare env name is treated as `<env>/*`. Standalone repos are reached via `--standalone` / `--all` and ignore `PATTERNS` — to operate on a single standalone repo, use raw git.

| Invocation | Operates on |
|------------|-------------|
| `winter ws <cmd>` | every env's project worktrees |
| `winter ws <cmd> alpha` | `alpha`'s project worktrees (== `alpha/*`) |
| `winter ws <cmd> alpha/winter` | one specific worktree |
| `winter ws <cmd> '*/winter'` | every env's `winter` worktree |
| `winter ws <cmd> 'alpha/*' 'beta/*'` | `alpha` + `beta` worktrees |
| `winter ws <cmd> --standalone` | every standalone repo (no project worktrees) |
| `winter ws <cmd> --all` | project worktrees + every standalone repo |
| `winter ws <cmd> '*/winter' --all` | every env's `winter` worktree + every standalone repo |

`fetch` and `pull` always include both pinned and non-pinned worktrees in the matched set. `push` excludes pinned worktrees by default (see Pinned-scope flags below).

Pinned-scope flags (`push` only — `fetch`/`pull` always include pinned):

| Flag | Effect |
|------|--------|
| _(default)_ | non-pinned worktrees only |
| `--include-pinned` | non-pinned + pinned |
| `--only-pinned` | pinned only |

Mutex rules: `--include-pinned` xor `--only-pinned` (push only); `--standalone` xor `--all`; `--standalone` rejects PATTERNS, and on `push` also rejects `--include-pinned` / `--only-pinned`.

Pattern syntax: `*` matches any chars within a segment (does not cross `/`); `?` matches one char. Quote patterns in your shell to prevent expansion.

**`pull` per-repo target ref.** Non-pinned project worktrees pull from `origin/<feature-branch>` (set by `winter ws connect`). Pinned project worktrees pull from `origin/<main-branch>` because they don't participate in feature branching. Standalone repos pull from whatever their local branch tracks.

**`pull` integration mode** (mutually exclusive, default `--ff-only`):

| Flag | Behavior |
|------|----------|
| `--ff-only` (default) | Fast-forward or report diverged — never produces a merge commit or rewrites history |
| `--merge` | Fall back to a 3-way merge commit when ff-only fails |
| `--rebase` | Replay local commits onto the upstream tip when ff-only fails |

`--autostash` (orthogonal) passes through to `git merge` / `git rebase`, which stash a dirty working tree before integrating and restore it after. If autostash fails, git aborts and the repo is reported as diverged.

**`push` per-repo target.** Non-pinned project worktrees push `HEAD:refs/heads/<feature-branch>`. Pinned project worktrees (when included via `--include-pinned` or `--only-pinned`) and standalone repos plain-push to whatever their local branch tracks (typically `origin/<main>`, but they will follow any custom upstream you set with `git branch --set-upstream-to`). Only repos with commits ahead of upstream are pushed.

`push` excludes pinned worktrees by default because pinned repos track the main branch and aren't part of the feature-push flow. Use `--include-pinned` when you've landed commits on a pinned repo's main branch and want to ship them, or `--only-pinned` to ship just those without touching feature branches.

**`sync` vs `pull`.** `sync` always targets `origin/main` and falls back to a merge commit when ff-only fails (so source checkouts stay aligned even when the env has drifted). `pull` always targets the *tracked* upstream — the feature branch for non-pinned worktrees, main for pinned, custom branches for standalone repos — and is ff-only by default. Use `sync` to bring main into a feature env; use `pull` to grab remote commits made on the feature branch.

## Repository commands (`winter repo`)

| Command | Usage | Purpose |
|---------|-------|---------|
| `winter repo list` | `winter repo list [--json]` | List all project and standalone repositories and their types |
| `winter repo status` | `winter repo status ENV REPO [--json]` | Detailed git status for one repo in a feature environment |

## Dashboard

```bash
winter dashboard
```

Interactive TUI showing workspace status, feature environments, and repo details. Navigate with keyboard.

## Drift warnings

Operations that iterate repos (`ws list`, `ws status`, `ws sync`, `ws fetch`, `ws pull`, `ws push`, `ws connect`, `ws disconnect`, `ws diff`, `repo list`) warn to stderr when the config and filesystem disagree:

- **Missing:** a declared project repo has no directory under `projects/` — run `winter ws init`
- **Undeclared:** a directory under `projects/` is not in the config — add it to `.winter/config.toml` or remove it

`winter ws init` treats both cases as actionable rather than a warning: missing repos are cloned; undeclared directories are left alone.

Drift detection currently covers project repos only. Missing or undeclared standalone repos are not warned about; if a `[[standalone_repository]]` entry's directory is missing, `winter ws init` clones it on the next run.

## Common workflows

### Bootstrap a new workspace
```bash
winter ws init              # clone every declared repo into projects/
winter ws init alpha        # create the alpha/ feature environment
```

### Check workspace state
```bash
winter ws status alpha
```

### Sync before starting work
```bash
winter ws sync alpha    # tries ff-only against origin/main, falls back to merge, reports diverged if both fail
```

### Pull remote feature-branch commits into the local env
```bash
winter ws pull alpha               # ff-only against origin/<feature-branch>; diverged repos reported, not touched
winter ws pull alpha --rebase      # ff or replay local commits onto upstream
winter ws pull alpha --autostash   # stash dirty tree first, restore after
```

### Start a new feature
```bash
winter ws init alpha                       # ensures alpha/ exists
winter ws connect alpha feature/my-feature
```

### Push completed work
```bash
winter ws push alpha                       # alpha's non-pinned worktrees
winter ws push alpha/winter                # one specific worktree
winter ws push 'alpha/*' 'beta/*'          # alpha + beta non-pinned worktrees
winter ws push --include-pinned            # all envs, pinned and non-pinned
winter ws push --all                       # all envs' non-pinned worktrees + standalone
```

### Update everything from remotes (no working-tree changes)
```bash
winter ws fetch --all                      # refresh refs for every env + standalone
```

### Review changes before committing
```bash
winter ws diff alpha --branch          # full branch diff vs main
winter ws diff alpha --staged          # staged changes only
winter ws diff alpha --repo my-app     # single repo
```

### Reuse a feature environment for a different feature
```bash
winter ws disconnect alpha
winter ws connect alpha feature/other-feature
```

### Propagate a config change
After adding a repo to the config or changing `cmd`/`git_excludes`, reconcile everything:
```bash
winter ws init --all
```
