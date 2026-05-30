# Project context — building winter, with winter

This workspace develops the **winter** framework and its extensions. Each project repo is itself a winter component: the CLI in `winter`, the conventions repo in `winter-harness`, tmux service orchestration in `winter-service-tmux`, the agentic workflow in `winter-workflow`, Codeberg issue tooling in `winter-codeberg`, product backlog tooling in `winter-product`.

## Project-level conventions

| Topic | Where to read |
|-------|---------------|
| Commit format, delivery, push rules | [contributing.md](./contributing.md) |
| Service orchestration in this workspace | [setup-tmux.sh](./setup-tmux.sh) (config) — and `winter-service-tmux:/index.md` for the conventions |

## Per-repo conventions

Each project repo ships its own `CONTRIBUTING.md` and `ai/` directory. Read the one for the repo you are touching before making changes. The workspace-level `contributing.md` above only covers the cross-repo flow (rebasing onto `origin/master`, conventional commits with scope, `Closes #N` footers).
