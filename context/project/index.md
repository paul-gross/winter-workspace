# Project context — building winter, with winter

This workspace develops the **winter** framework and its extensions. Each project repo is itself a winter component: the CLI in `winter`, the conventions repo in `winter-harness`, tmux and docker service orchestration in `winter-service-tmux` and `winter-service-docker`, the agentic workflow in `winter-workflow`, GitHub issue tooling in `winter-github`, product backlog tooling in `winter-product`, and the public documentation site in `winter-docs`.

## Project-level conventions

| Topic | Where to read |
|-------|---------------|
| Commit format, delivery, push rules | [contributing.md](./contributing.md) |
| Service orchestration in this workspace | Both providers are bound via `[capabilities]`. tmux manifest: [config.toml](../../.winter/config/winter-service-tmux/config.toml) + [layout-hook.sh](../../.winter/config/winter-service-tmux/layout-hook.sh); docker manifest: [config.toml](../../.winter/config/winter-service-docker/config.toml) + compose files. Conventions in `winter-service-tmux:/index.md` and `winter-service-docker:/index.md`; [project-setup.md](./project-setup.md) has the both-provider setup. |

## Per-repo conventions

Each project repo ships its own `CONTRIBUTING.md` and `context/` directory. Read the one for the repo you are touching before making changes. The workspace-level `contributing.md` above only covers the cross-repo flow (rebasing onto `origin/master`, conventional commits with scope, `Closes #N` footers).
