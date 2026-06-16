# Contributing

## Commit messages

Use Conventional Commits with a scope:

    <type>(<scope>): <description>

    [optional body]

    Co-Authored-By: Claude <noreply@anthropic.com>

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

    Co-Authored-By: Claude <noreply@anthropic.com>

Use `Closes #N` (or `Fixes #N` / `Resolves #N`) for issues this commit
finishes. Use `Refs #N` to cross-link an issue this commit relates to
but doesn't close. Always use the short `#N` form, not the full
issue URL — only the short form triggers GitHub's auto-close and
back-link behavior.

A bare `#N` always resolves against **the repo the commit lands in**,
not the repo the issue was filed in. In this workspace a fix often
lands in a different repo than the one tracking it (e.g. a
`winter-workflow` issue resolved in `winter-harness`), so before
writing the footer, confirm which repo the issue lives in. When it
isn't the commit's repo, **scope the reference** with the
`owner/repo#N` form — `Closes paul-gross/winter-workflow#21` to close
it (cross-repo auto-close works given push access to the target repo)
or `Refs paul-gross/winter-workflow#21` to link without closing. A
bare `#21` there silently targets the commit's repo and leaves the
real issue open.

## Pre-commit checks

No automated gate (no PR review, no CI). Each project repo documents
its own pre-push convention in its `context/` directory. For Python repos,
the canonical rules live at `winter-harness:/standards/linting.md` and
`winter-harness:/standards/typechecking.md` — run `mise run format`,
`mise run lint`, and `mise run typecheck` before pushing.

## Delivery

- Default branch: `master` on every repo.
- No PR/MR flow and no feature branches — completed work is pushed
  directly to `origin/master`. Always rebase onto the latest
  `origin/master` first so history stays linear and each landed unit of
  work is a single commit (one feature or fix per commit, no merge
  commits).
- See `workspace:/context/worktree-ops.md` for the exact git commands per
  worktree (sync, push, complete).

## Post-delivery

Nothing automated — no deploys, no tags, no changelog.
