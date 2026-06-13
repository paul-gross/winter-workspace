# `winter ws merge` — fold an arbitrary ref into matched worktrees

`merge` is a sibling of `pull` with an explicit source ref. Read [`pull`](./pull.md) for the shared behavior (autostash semantics, abort-on-conflict reporting) and the [pattern and scope vocabulary](./patterns.md) for patterns and scope flags; the deltas are:

- `SOURCE_REF` is an explicit positional arg, applied verbatim per repo. `pull` uses each worktree's tracked upstream.
- `--no-ff` replaces `--rebase` in the mode trio — force a merge commit even when fast-forward is possible (matches `git merge --no-ff`). `--ff-only` (default) and `--merge` behave exactly as in `pull`.
- No fetch. `pull` fetches first; `merge` doesn't, because `SOURCE_REF` is often a local branch. Run `winter ws fetch` first if you need fresh refs.
- Pinned worktrees are included by default (`pull` always includes them; `push` excludes by default). Opt out with `--exclude-pinned` or restrict to pinned with `--only-pinned`.

```bash
winter ws merge alpha gamma            # merge alpha into gamma's project worktrees (== 'gamma/*')
winter ws merge master gamma           # merge master into gamma's project worktrees
winter ws merge origin/master gamma    # explicit remote ref also accepted
winter ws merge master '*/winter'      # merge master into every env's winter worktree
winter ws merge master '*/*' --all     # merge master into every env's worktrees + every standalone
```

A target `PATTERN` is required whenever project worktrees are in scope — there is no implicit "all worktrees" default. `winter ws merge alpha` with no pattern is rejected; pass `'*/*'` to fan a source ref across every env's every worktree on purpose.

**Per-repo outcomes** (literal CLI output):

| Outcome | Meaning |
|---------|---------|
| `up-to-date` | Source ref already reachable from HEAD; nothing to do |
| `fast-forwarded` | HEAD advanced to source ref without a merge commit |
| `merged (merge commit created)` | A merge commit was created (only under `--merge` or `--no-ff`) |
| `diverged: +N/-N` | `--ff-only` refusal, or a conflict during `--merge`/`--no-ff` that aborted the merge |
| `skipped: source ref not found` | The source ref doesn't resolve in this repo |

Exit code is `0` when every selected repo merged cleanly (`up-to-date`, `fast-forwarded`, or `merged (merge commit created)`), and `1` if any repo diverged or had a missing source ref. Cross-repo atomicity is not provided — if one repo merges cleanly and another diverges, the clean merge stays. Conflicts that abort don't leave a merge in progress; use raw `git reset --hard ORIG_HEAD` per repo if you want to undo a fast-forward or merge commit.

**When to use `merge` vs `pull`:**

- `merge` — the source ref isn't the worktree's tracked upstream (env-to-env, explicit branch). Offline; doesn't fetch.
- `pull` — integrate the tracked upstream (feature branch for non-pinned, main for pinned). Fetches first.
