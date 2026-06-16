# GitHub

This workspace uses [GitHub](https://github.com) as its primary git forge for repos under the [`paul-gross`](https://github.com/paul-gross) org. Issue management runs through the [`gh`](https://cli.github.com/) CLI plus the `/wg-issue` skill from the `winter-github` extension.

## Tooling

- **`gh`** — official GitHub CLI. Auth via `gh auth login --hostname github.com` (interactive) or `echo "<token>" | gh auth login --hostname github.com --with-token` (non-interactive). Token is stored in the OS keyring.
- **`/wg-issue`** — drafts and files a GitHub issue in the [AI-native format](../.winter/ext/github/context/issue-format.md).
- **GitHub API** — reached via `gh api <path>` for operations the CLI doesn't expose directly (bulk relabeling, comment edits, repo-setting migrations). No separate token plumbing — `gh api` reuses the same auth context.

## Labels

Every `paul-gross/winter*` repo carries the same canonical label set. Two families — **type** and **complexity** — matching the metadata block in the issue format.

| Name | Color | Description |
|------|-------|-------------|
| `type:bug` | `d73a4a` | Something is broken |
| `type:chore` | `cccccc` | Maintenance, housekeeping |
| `type:feature` | `0e8a16` | New capability |
| `type:refactor` | `1d76db` | Internal restructuring, no behavior change |
| `type:spike` | `5319e7` | Time-boxed investigation |
| `type:epic` | `c77dff` | Parent of a set of child issues |
| `complexity:trivial` | `ededed` | Author estimate: trivial |
| `complexity:small` | `fbca04` | Author estimate: small |
| `complexity:large` | `e99695` | Author estimate: large |

`paul-gross/winter` is the reference repo — when drift is suspected, diff against it. When creating a new winter-ecosystem repo on GitHub, mirror this set before filing the first issue.

## Issues

### Filing

Use `/wg-issue`. The skill drafts from conversation context, confirms the target repo, probes existing labels, and files via `gh issue create`. Format spec: [issue-format.md](../.winter/ext/github/context/issue-format.md).

### Epics

Large work that decomposes into several child issues is filed as an **epic** — a parent issue with its children linked as GitHub sub-issues. The convention (title prefixes, the `type:epic` label, metadata, and link commands) lives in [epics.md](../.winter/ext/github/context/epics.md).

### Closing

Two ways:

1. **From a commit** — include `Fixes #N` (or `Closes #N`) in the commit message body. GitHub auto-closes when the commit lands on the default branch. A bare `#N` resolves against **the repo the commit lands in**, not the repo the issue was filed in — and work here often lands in a different repo than the one tracking it (e.g. a `winter-workflow` issue fixed in `winter-harness`), so a bare `#N` silently links, and may close, the wrong issue while the real one stays open. Confirm which repo the issue lives in; when it isn't the commit's repo, scope the reference as `paul-gross/<repo>#N` — `Closes paul-gross/winter-workflow#21` to close it (cross-repo auto-close works given push access) or `Refs paul-gross/winter-workflow#21` to link without closing.
2. **Manually via gh** — `gh issue close <N> --repo paul-gross/<repo>`. Use when work merged without a fix-ref, or when abandoning the issue.

Don't close silently in the web UI — commit references leave a paper trail. Leave a brief closing comment if the linked commit doesn't make context obvious.
