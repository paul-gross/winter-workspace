# `winter ws init` — reconcile the workspace against the config

For the rest of the family, see the [`winter ws` hub](./index.md).

One idempotent command with three modes. Safe to re-run any time.

| Form | What it reconciles |
|------|--------------------|
| `winter ws init` | Source checkouts in `projects/` and standalone repos. |
| `winter ws init <name>` | The `./<name>/` feature environment. |
| `winter ws init --all` | Source checkouts, standalones, and every existing feature environment. |

Each mode applies the same per-repo reconcile steps (git identity, excludes, `cmd` list, extension processing, pinned-repo tracking on worktrees). See [worktree-ops.md](../../../worktree-ops.md) for the full step list and the pinned-repo specifics.

Greek letters (`alpha`, `beta`, …) are the suggested convention for feature environment names because they carry a fixed port-offset index 1..24. Any other valid directory name is accepted and gets a deterministic SHA-1-derived index in the range 26..281 (index 25 is reserved as a buffer). Hash collisions among non-Greek names are possible but unlikely.
