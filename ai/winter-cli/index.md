# Winter CLI

The `winter` command is a workspace-level tool for managing worktrees and repositories. It reads configuration from `.winter/config.toml` and operates across every repo in the workspace at once. This is the hub: read it first, then open the one per-topic file you need.

## When to use the CLI vs raw git

**Use the CLI** for operations that span multiple repos — init, status, fetch, pull, connect, push, diff. The CLI handles pinned repos, parallel fetching, source checkout fast-forwarding, and idempotent setup automatically.

**Use raw git** for single-repo operations — staging files, committing, resolving conflicts, interactive rebase, branch inspection. The CLI doesn't replace git for per-repo work.

**Strongly recommended:** read **[usage/index.md](./usage/index.md)** first — the command reference index is a high-level map of everything the CLI can do. Skim it to learn the surface, then open the one topic you need.

## Root flags

`winter --version` prints the installed CLI version (sourced from package metadata, so it tracks the running source) and exits 0. `winter --help` lists every command and root flag.

## What the CLI can do

The surface is two command groups plus five standalone commands:

- **`winter ws …`** — reconcile the workspace or a feature env against the config (`init`), inspect state (`status`, `list`, `worktrees`, `diff`, `index`), move commits between remotes and worktrees (`fetch`, `pull`, `push`, `merge`), and manage env lifecycle (`connect`, `disconnect`, `checkout`, `destroy`, `prune`).
- **`winter repo …`** — add, remove, and list the repositories declared in the config.
- **`winter dashboard`** — interactive TUI for workspace status, with remappable keybindings.
- **`winter service <action> <env>`** — a stable `up`/`down`/`status`/`restart`/`logs` interface that dispatches to whichever orchestrator extension the workspace registers.
- **`winter doctor`** — preflight health checks.
- **`winter lint`** — convention checks.
- **`winter graph`** — the module dependency graph.

Most flows are multi-repo: a single `winter ws` invocation fans out over every matched worktree in parallel, honoring pinned-repo rules. Commands accept segment-aware glob `PATTERNS` over `<env>/<repo>`, emit `--json` for tooling, and never touch the network unless the command's purpose is to (`fetch`/`pull`/`push`, or `status --fetch`).

## Routing table

| Topic | Read when… |
|-------|------------|
| [Command reference](./usage/index.md) | …you need to run any `winter` command — the per-topic routing index for `ws`, `repo`, `dashboard`, `service`, `doctor`, `lint`, and `graph`. |
| [Common workflows](./workflows.md) | …you want a ready-made command sequence for a routine multi-step operation — bootstrap, start a feature, merge main, push, tear down. |
| [Resilience & drift](./resilience.md) | …you hit a flaky-network retry, a hung remote git call, or a config↔filesystem drift warning, and want the cross-cutting behavior behind it. |
| [Install & configure](./setup.md) | …you're installing winter or editing `.winter/config.toml` — schema, local overlay, and extensions. |
| [Author a TUI plugin](winter-harness:/python/plugin-author.md) | …you're extending the dashboard from a `plugin.py` — badges, screens, keybound actions. |
