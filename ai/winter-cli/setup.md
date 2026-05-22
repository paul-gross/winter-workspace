# Winter CLI — Setup

Installation and configuration reference. For day-to-day command usage, see [usage.md](./usage.md).

## Installation

```bash
./tools/winter-cli/install.sh
```

This copies the `winter` wrapper to `~/.local/bin/`. The wrapper auto-discovers the workspace root by searching upward for `.winter/config.toml` + `tools/winter-cli/`, then runs via `mise` and `uv` — no manual virtualenv setup needed.

## Configuration

Winter loads two files and merges them:

- `.winter/config.toml` — committed workspace config (repo list, excludes, defaults)
- `.winter/config.local.toml` — gitignored overlay for per-user settings (git identity)

### Shared config (`.winter/config.toml`)

```toml
session_prefix = "my-project"       # tmux session prefix
main_branch = "main"                # workspace-default main branch (per-repo override below)
adopt_extensions = "winter"         # how aggressively standalone repos contribute skills/agents

# Entries appended to every repo's .git/info/exclude on `winter ws init`.
git_excludes = ["*.Local.csproj"]

# Project repositories — cloned to projects/ and worktreed into Greek-letter dirs.
# Entries appear in CLI and TUI output in the order they're listed here, so put
# high-priority repos first.
[[project_repository]]
name = "web"                       # directory name under projects/ — overrides what would be derived from `url`
url = "git@example.com:org/winter-app.git"
cmd = ["pnpm install"]             # run after clone and in every worktree
git_excludes = [".env.development.local"]   # per-repo excludes, merged with workspace-wide

[[project_repository]]
name = "api"
url = "git@example.com:org/winter-api.git"
main_branch = "development"        # per-repo override of the top-level main_branch
cmd = ["dotnet restore"]

# Pinned repos always track origin/main and are skipped during feature branching.
[[project_repository]]
name = "shared-tools"
url = "git@example.com:org/shared-tools.git"
pinned = true

# Standalone repositories — cloned to the workspace root (or `path`), no worktree,
# no feature branching. Useful for winter extensions (skills/agents) and any repo
# you want available alongside project repos but not multiplied per-feature.
[[standalone_repository]]
name = "winter-backlog"
url = "git@github.com:user/winter-backlog.git"
prefix = "wsb"                     # optional symlink-prefix override; see "Extensions" below
path = "extensions/winter-backlog" # optional; relative to the workspace root, defaults to `name`
```

### Local overlay (`.winter/config.local.toml`)

```toml
[git]
user.name = "John Doe"
user.email = "john.doe@example.com"
```

The overlay uses the same schema as the shared config. Keys in the overlay override the shared config key-by-key. The `[git]` identity is applied to every repo winter-cli manages during `winter ws init`.

### Display names and ordering

`name` doubles as the directory under `projects/` and as the user-facing label everywhere a repo is shown (grid columns, status tables, sync/push/diff headers). When `name` is omitted, it's derived from the trailing path segment of `url` (with `.git` stripped). Set `name` explicitly when you want a friendlier label than the canonical repo name.

Repos appear in CLI tables and the TUI grid in the order they're declared in `.winter/config.toml`. Put the repos you work with most often at the top.

### Implicit Repositories

The `workspace` repo is discovered implicitly — it doesn't appear in `[[project_repository]]` or `[[standalone_repository]]`. Winter detects it from the filesystem: the workspace itself is the repo this CLI is invoked from.

## Extensions

Standalone repositories can opt into contributing skills and agents to the workspace's `.claude/` directory by shipping a `winter-ext.toml` file at the repo root.

### `winter-ext.toml` schema

```toml
name = "winter-backlog"        # default symlink prefix when no override is set
prefix = "wsb"                 # optional shorter prefix; takes precedence over `name`
skills_dir = "skills"          # optional; explicit path overrides default discovery
agents_dir = "agents"          # optional; explicit path overrides default discovery
```

The final symlink prefix is resolved with this precedence: `prefix` on the workspace config entry > `prefix` in `winter-ext.toml` > `name` in `winter-ext.toml` > the standalone repo's directory name.

### What gets symlinked

When `skills_dir` and `agents_dir` aren't set explicitly, winter searches for them in this order and uses the first that exists:

- `skills/` then `.claude/skills/`
- `agents/` then `.claude/agents/`

That covers both the winter convention (top-level `skills/`/`agents/`) and the Claude Code convention (`.claude/skills/`/`.claude/agents/`), so a vanilla Claude Code repo can be adopted as an extension without modification. Setting `skills_dir`/`agents_dir` explicitly in `winter-ext.toml` skips the fallback and uses exactly the declared path.

For each subdirectory under the resolved skills root, winter creates a symlink at `.claude/skills/<prefix>-<dir>` pointing to it. For each `.md` file or subdirectory under the resolved agents root, winter creates a symlink at `.claude/agents/<prefix>-<name>`.

The workspace `.gitignore` is updated with a marker-bracketed block per extension:

```
# >>> winter-backlog (managed by winter)
/winter-backlog/
.claude/skills/wsb-*
.claude/agents/wsb-*
# <<< winter-backlog
```

### Frontmatter convention

Claude Code lets a SKILL.md frontmatter `name` field override the directory name during skill discovery. That defeats the prefix-by-symlink design, so winter requires extension SKILL.md files to **omit the `name` field** — letting the directory name (which winter controls via the symlink) be authoritative. Winter validates this on install and refuses if any SKILL.md sets `name`.

### Extension hooks

Extensions can also declare lifecycle hooks in `winter-ext.toml`:

```toml
[hooks]
on_env_init    = "./hooks/init-worktree.sh"
on_env_destroy = "./hooks/destroy-worktree.sh"
```

- `on_env_init` fires after `winter ws init <env>` creates every per-repo worktree and seeds `.winter.env`. Use it to provision per-env state (tmux sessions, databases, watchers).
- `on_env_destroy` fires *before* `winter ws destroy <env>` removes any per-repo worktree or the env directory. Use it to release whatever `on_env_init` provisioned.

Hook scripts must be **relative paths inside the extension directory** (so the extension owns its scripts; winter resolves them against the extension root).

#### Hook env-var contract

Every hook is invoked with:

| Var | Meaning |
|-----|---------|
| `WINTER_WORKSPACE_DIR` | Absolute path to the workspace root. |
| `WINTER_EXT_DIR` | Absolute path to this extension's clone (the dir containing `winter-ext.toml`). |
| `WINTER_EXT_PREFIX` | The resolved symlink prefix for this extension (`wf`, `wst`, …). |
| `WINTER_ENV` | The env name (`alpha`, `beta`, …). |
| `WINTER_ENV_INDEX` | The port-offset index (1..24 for Greek letters, hashed 26..281 otherwise). |
| `WINTER_PORT_BASE` | `4000 + 100 * WINTER_ENV_INDEX`. |

The hook's **cwd is the env root** (`<workspace>/<env>/`). Hooks should read these env vars rather than parse `argv`.

**Strict vs non-strict on destroy.** By default, a non-zero exit from a destroy hook is logged and the teardown continues so a broken hook doesn't trap an env on disk. Pass `--strict` to `winter ws destroy` (or set it in CI/scripted use) when a hook failure must surface as a user-actionable error before any worktree is removed.

### `adopt_extensions` modes

The top-level `adopt_extensions` field controls when winter processes a standalone repo's skills and agents:

| Value | Behavior |
|-------|----------|
| `winter` (default) | Process only standalone repos that have a `winter-ext.toml` at the repo root. SKILL.md frontmatter is strictly validated. |
| `all` | Process any standalone repo with `skills/`, `agents/`, `.claude/skills/`, or `.claude/agents/` directories, with or without a manifest. Frontmatter validation downgrades from refuse-to-warn — collisions become the user's problem. |
| `none` | Skip all extension processing. Standalone repos are still cloned, but no symlinks are created. |
