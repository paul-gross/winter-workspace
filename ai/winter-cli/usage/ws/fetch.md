# `winter ws fetch` — refresh remote-tracking refs

Fetches `origin` for matched project worktrees in parallel and honors pinned-repo rules. Shares the [pattern and scope vocabulary](./patterns.md) with `pull` / `push` / `merge`; this file covers only fetch-specific behavior. For the family, see the [`winter ws` hub](./index.md).

**`fetch` and source checkouts.** Beyond refreshing remote-tracking refs, `fetch` fast-forwards each matched source checkout's local main (`projects/<repo>`) to `origin/<main-branch>`. Worktrees of a project repo share the source checkout's `.git`, so this is a single fetch per repo that both updates the shared refs every worktree sees and keeps the base `winter ws init` branches new envs off of current. Feature worktrees are never touched. A diverged source checkout main (it should only ever track main) is reported as a failed fetch for that repo.
