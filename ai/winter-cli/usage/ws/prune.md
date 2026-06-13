# `winter ws prune` — remove orphaned disk state

For the rest of the family, see the [`winter ws` hub](./index.md).

`winter ws prune` finds and removes state for repos no longer in the workspace config:

- Orphan project clones under `projects/`.
- Orphan standalone clones referenced by stale entries in `.git/info/exclude`.
- Broken symlinks under `.claude/skills/` and `.claude/agents/`.

Refuses to delete repos with uncommitted changes or attached worktrees. Use `--dry-run` to preview, `--force` to skip the interactive confirmation.
