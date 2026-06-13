# `winter ws pull` — integrate the tracked upstream

Fetches, then integrates each matched worktree's tracked upstream (ff-only by default). Shares the [pattern and scope vocabulary](./patterns.md) with `fetch` / `push` / `merge`; this file covers only pull-specific behavior. For the family, see the [`winter ws` hub](./index.md).

**Per-repo target ref.** Non-pinned project worktrees pull from `origin/<feature-branch>` (set by `winter ws connect`). Pinned project worktrees pull from `origin/<main-branch>` because they don't participate in feature branching. Standalone repos pull from whatever their local branch tracks.

**Integration mode** (mutually exclusive, default `--ff-only`):

| Flag | Behavior |
|------|----------|
| `--ff-only` (default) | Fast-forward or report diverged — never produces a merge commit or rewrites history |
| `--merge` | Fall back to a 3-way merge commit when ff-only fails |
| `--rebase` | Replay local commits onto the upstream tip when ff-only fails |

`--autostash` (orthogonal) passes through to `git merge` / `git rebase`, which stash a dirty working tree before integrating and restore it after. If autostash fails, git aborts and the repo is reported as diverged.
