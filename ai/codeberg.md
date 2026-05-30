# Codeberg

This workspace uses [Codeberg](https://codeberg.org) (a Forgejo instance) as its primary git forge. All `pgross/winter*` repositories live there, and issue management runs through the [`tea`](https://gitea.com/gitea/tea) CLI plus the `/wc-issue` skill from the `winter-codeberg` extension.

## Tooling

- **`tea`** — CLI for Forgejo / Gitea. Auth via `tea login add --name codeberg --url https://codeberg.org --token <token>`. Token is stored at `~/.config/tea/config.yml`.
- **`/wc-issue`** — drafts and files a Codeberg issue in the [AI-native format](../.winter/ext/codeberg/ai/issue-format.md).
- **Forgejo API** — used directly (via `curl` + the same token) for operations `tea` doesn't cover, notably **relabeling existing issues**. `tea issues` only has `list`, `create`, `reopen`, `close`.

## Labels

Every `pgross/winter*` repo carries the same canonical label set. Two families — **type** and **complexity** — matching the metadata block in the issue format.

| Name | Color | Description |
|------|-------|-------------|
| `type:bug` | `d73a4a` | Something is broken |
| `type:chore` | `cccccc` | Maintenance, housekeeping |
| `type:feature` | `0e8a16` | New capability |
| `type:refactor` | `1d76db` | Internal restructuring, no behavior change |
| `type:spike` | `5319e7` | Time-boxed investigation |
| `complexity:trivial` | `ededed` | Author estimate: trivial |
| `complexity:small` | `fbca04` | Author estimate: small |
| `complexity:large` | `e99695` | Author estimate: large |

`pgross/winter` is the reference repo — when drift is suspected, diff against it. When creating a new winter-ecosystem repo, mirror this set before filing the first issue.

## Issues

### Filing

Use `/wc-issue`. The skill drafts from conversation context, confirms the target repo, probes existing labels, and files via `tea issue create`. Format spec: [issue-format.md](../.winter/ext/codeberg/ai/issue-format.md).

### Closing

Two ways:

1. **From a commit** — include `Fixes #N` (or `Closes #N`) in the commit message body. Codeberg auto-closes when the commit lands on the default branch.
2. **Manually via tea** — `tea issues close <N> --repo pgross/<repo>`. Use when work merged without a fix-ref, or when abandoning the issue.

Don't close silently in the web UI — commit references leave a paper trail. Leave a brief closing comment if the linked commit doesn't make context obvious.
