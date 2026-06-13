# `winter ws destroy` — tear down a feature env

For the rest of the family, see the [`winter ws` hub](./index.md). `winter ws destroy ENV` is the symmetric counterpart to [`winter ws init ENV`](./init.md):

1. **Safety check** — refuses on missing env path or dirty worktrees (override with `--force`).
2. **Hooks** — fires every extension's `on_env_destroy` hook (mirror of `on_env_init`). With `--strict`, a non-zero hook exit aborts the teardown; without it, hook failures are logged and teardown proceeds.
3. **Worktree removal** — `git worktree remove` for every per-repo worktree.
4. **Env cleanup** — removes the env directory and strips the matching `# >>> winter-dir/<env>` block from the workspace's `.git/info/exclude`.

Use `--dry-run` to preview the plan with no side effects.

**Prefer this over `rm -rf <env>/` + manual `git worktree remove`.** Manual removal bypasses `on_env_destroy` hooks the same way manual env creation bypasses `on_env_init` — extensions that need to clean up per-env state (tmux sessions, watchers, provisioned DBs) get skipped.
