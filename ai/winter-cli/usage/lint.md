# `winter lint` — convention checks

For the hub and the rest of the command surface, see [../index.md](../index.md).

```bash
winter lint                # the whole workspace (same as --all)
winter lint <repo>         # one repo by name
winter lint <env>          # every worktree in a feature env
winter lint --changed      # only the dirty / un-pushed files in the current repo
winter lint --all --json   # NDJSON event stream
```

Runs winter-ecosystem **convention** checks — path notation, agent frontmatter, module boundaries, and the like — as opposed to `winter doctor`, which checks workspace *materialization* (is this clone wired up correctly). The two are complementary: `doctor` answers "is the workspace healthy", `lint` answers "does the content follow winter's rules".

`winter lint` is a **dispatcher, not a checker** — it runs the built-in core checks bundled with winter-cli plus the lint scripts contributed by installed extensions (and an optional workspace-level one) over the selected scope, and aggregates their findings. It contains no check logic itself. The core checks always run, so even a workspace with no lint-contributing extension still gets module-extractability enforcement; a workspace with no contributed *scripts* lints only with the core checks. Each finding reports `pass`, `warn`, or `fail` with an optional `file:line` location and a remediation hint shown under failures. Exit code is `0` when nothing failed (warnings allowed), `1` if any check failed — usable in CI and pre-push.

**Scope** selects which content the checks run over (the resolved paths are handed to each check; the check decides which it recognizes):

- a **repo name** — that project / standalone repo's directory.
- an **env name** — every project worktree directory inside the env.
- `--all` (the default) — the whole workspace tree, rooted at the workspace root.
- `--changed` — files that are dirty or in un-pushed commits in the git repository containing the current directory. Run it from the repo or worktree you're about to push.

A name that matches both a repo and an env is rejected as ambiguous; `--all` and `--changed` are mutually exclusive with each other and with a name.

**Core checks** are built into winter-cli and always run (currently module extractability); their findings appear under a `[core]` source group. **Workspace checks** are contributed via a top-level `lint` field in `.winter/config.toml`; **extension checks** via the same field in an extension's `winter-ext.toml`. The contributed fields take a single script path or a list, so one source can contribute several distinct checks. All follow the same script contract as doctor probes, plus the scope env vars — see [setup.md#lint-checks](../setup.md#lint-checks). Each check also receives `WINTER_CLI`, the path to the running CLI, so it can call back for workspace-wide data it can't derive from its own scope — see [graph.md](./graph.md).

`--json` emits one NDJSON object per line: `{"type": "started", "scope": ..., "label": ..., "paths": [...]}` once, `{"type": "finding", "source": ..., "check": ..., "status": ..., "message": ..., "file": ..., "line": ..., "remediation": ...}` per finding, then `{"type": "finished", "contributors": N, "total": N, "fails": N, "warns": N}`. `contributors` is the number of lint scripts that ran — `0` means nothing was contributed.
