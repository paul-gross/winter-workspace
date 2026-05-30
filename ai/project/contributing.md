# Contributing

## Commit messages

Use Conventional Commits with a scope:

    <type>(<scope>): <description>

    [optional body]

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `style`, `ai`.
Scope is usually the repo name (e.g. `winter-cli`, `winter-product`) or a
subsystem within it.

The `/wf-commit` skill (from the `winter-workflow` extension) generates
commits in this exact format — prefer it over hand-writing messages.

### Issue references

When a commit completes a GitHub issue, include a `Closes #N` footer
on its own line just above the `Co-Authored-By` trailer. GitHub
recognizes the keyword and auto-closes the issue once the commit
lands on the default branch, and links the issue back to the commit
SHA on both sides.

    refactor(winter-cli): migrate WorkspaceHandler tables to render_table

    [optional body]

    Closes #2

    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

Use `Closes #N` (or `Fixes #N` / `Resolves #N`) for issues this commit
finishes. Use `Refs #N` to cross-link an issue this commit relates to
but doesn't close. Always use the short `#N` form, not the full
issue URL — only the short form triggers GitHub's auto-close and
back-link behavior.

For issues that live in a different GitHub repo, use the
`owner/repo#N` form (e.g. `Closes paul-gross/winter-codeberg#7`).

## Pre-commit checks

No automated gate (no PR review, no CI). Each project repo documents
its own pre-push convention in its `ai/` directory. For Python repos,
the canonical rules live at `winter-harness:/python/linting.md` and
`winter-harness:/python/typechecking.md` — run `mise run format`,
`mise run lint`, and `mise run typecheck` before pushing.

## Delivery

- Default branch: `master` on every repo.
- No PR/MR flow and no feature branches — completed work is pushed
  directly to `origin/master`. Always rebase onto the latest
  `origin/master` first so history stays linear and each landed unit of
  work is a single commit (one feature or fix per commit, no merge
  commits).
- See `workspace:/ai/worktree-ops.md` for the exact git commands per
  worktree (sync, push, complete).

## Post-delivery

Nothing automated — no deploys, no tags, no changelog.
