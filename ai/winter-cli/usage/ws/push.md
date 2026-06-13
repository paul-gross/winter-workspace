# `winter ws push` — push matched worktrees to their upstream

Pushes each matched worktree to its tracked upstream in parallel; only repos with commits ahead of upstream are pushed. Shares the [pattern and scope vocabulary](./patterns.md) with `fetch` / `pull` / `merge`; this file covers only push-specific behavior. For the family, see the [`winter ws` hub](./index.md).

**Per-repo target.** Non-pinned project worktrees push `HEAD:refs/heads/<feature-branch>`. Pinned project worktrees (when included via `--include-pinned` or `--only-pinned`) and standalone repos plain-push to whatever their local branch tracks (typically `origin/<main>`, but they will follow any custom upstream you set with `git branch --set-upstream-to`). Only repos with commits ahead of upstream are pushed.

`push` excludes pinned worktrees by default because pinned repos track the main branch and aren't part of the feature-push flow. Use `--include-pinned` when you've landed commits on a pinned repo's main branch and want to ship them, or `--only-pinned` to ship just those without touching feature branches.

**Output signal — pinned repos skipped.** When the only worktrees with commits to push in an env are pinned (e.g. a workspace where every repo is pinned and tracks `origin/<main>` directly), a bare `winter ws push <env>` pushes nothing and emits a skip line: `! <env>: N pinned repo(s) with commits skipped — use --include-pinned or --only-pinned`. Re-run with `--include-pinned` (or `--only-pinned`) to ship them — or push directly with git per the workspace's delivery convention. Don't read this as "nothing to push"; it means the commits exist but the default scope excluded them.
