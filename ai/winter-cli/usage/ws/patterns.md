# `winter ws` fetch / pull / push / merge — patterns and scope

Shared vocabulary for the four remote-sync commands. Each command's own file ([fetch](./fetch.md), [pull](./pull.md), [push](./push.md), [merge](./merge.md)) covers its deltas; this file is the single source for `PATTERNS`, scope flags, and pinned-scope rules. For the family, see the [`winter ws` hub](./index.md).

All four commands accept any number of segment-aware glob `PATTERNS` over `<env>/<repo>`. A bare env name is treated as `<env>/*`. Standalone repos are reached via `--standalone` / `--all` and ignore `PATTERNS` — to operate on a single standalone repo, use raw git. `merge` takes a required `SOURCE_REF` as its first positional, then patterns trail; the other three take patterns only.

`fetch` / `pull` / `push` default to `*/*` when no patterns are given (operate on every env's project worktrees). **`merge` is the exception**: it requires an explicit pattern whenever project worktrees are in scope — bare `winter ws merge <ref>` (and `winter ws merge <ref> --all`) are rejected, because silently folding `SOURCE_REF` into every worktree is rarely intended. Pass `'*/*'` to opt into that fan-out on purpose. The table rows below assume `merge` carries an explicit pattern; the `<cmd>` and `<cmd> --all` rows (no pattern) apply to `fetch` / `pull` / `push` only.

| Invocation | Operates on |
|------------|-------------|
| `winter ws <cmd>` | every env's project worktrees (not `merge` — see above) |
| `winter ws <cmd> alpha` | `alpha`'s project worktrees (== `alpha/*`) |
| `winter ws <cmd> alpha/winter` | one specific worktree |
| `winter ws <cmd> '*/winter'` | every env's `winter` worktree |
| `winter ws <cmd> 'alpha/*' 'beta/*'` | `alpha` + `beta` worktrees |
| `winter ws <cmd> --standalone` | every standalone repo (no project worktrees) |
| `winter ws <cmd> --all` | project worktrees + every standalone repo (`merge` needs an explicit pattern, e.g. `'*/*' --all`) |
| `winter ws <cmd> '*/winter' --all` | every env's `winter` worktree + every standalone repo |

Pinned-scope behavior per command:

| Command | _(default)_ | Opt-in / opt-out flags |
|---------|-------------|------------------------|
| `fetch` / `pull` | both | n/a — always include both |
| `push` | non-pinned only | `--include-pinned` (+ pinned), `--only-pinned` (pinned only) |
| `merge` | both | `--exclude-pinned` (non-pinned only), `--only-pinned` (pinned only) |

Mutex rules: pinned-scope flags are mutually exclusive within a command (`--include-pinned` xor `--only-pinned` for push; `--exclude-pinned` xor `--only-pinned` for merge); `--standalone` xor `--all`; `--standalone` rejects PATTERNS, and on `push`/`merge` also rejects the pinned-scope flags.

Pattern syntax: `*` matches any chars within a segment (does not cross `/`); `?` matches one char. Quote patterns in your shell to prevent expansion.
