# Winter meta workspace

A winter workspace for developing winter itself.

This repo is a winter workspace configured with the winter framework and its extensions as its project repositories, so they can all be developed in coordinated feature environments. It's the dogfooding setup — winter, used to build winter.

> **Note:** while this is technically eating our own dogfood, please do not eat yellow snow.

## Project repos

Declared in `.winter/config.toml` and managed by `winter ws init`:

- **[winter](https://github.com/paul-gross/winter)** — the framework itself (Python CLI, workspace skills, docs)
- **[winter-harness](https://github.com/paul-gross/winter-harness)** — extension: Python conventions, exemplars, README guide
- **[winter-service-tmux](https://github.com/paul-gross/winter-service-tmux)** — extension: tmux-based service orchestration (`./up`/`./down`/`./status`)
- **[winter-product](https://github.com/paul-gross/winter-product)** — extension: product planning agents and skills
- **[winter-workflow](https://github.com/paul-gross/winter-workflow)** — extension: agentic workflow conventions and the `/wf-commit` skill
- **[winter-github](https://github.com/paul-gross/winter-github)** — extension: AI-native GitHub issue format and the `/wg-issue` skill
- **[winter-docs](https://github.com/paul-gross/winter-docs)** — the public documentation site

Each one is materialised in two or three places:

- `projects/<name>/` — pinned source checkout, always on `master`. Read-only by convention.
- `<env>/<name>/` — feature worktrees on Greek-letter branches (`alpha`, `beta`, ...). Where actual edits happen.
- For the extensions, also `./.winter/ext/<short-name>/` (e.g. `harness`, `service-tmux`) — a standalone clone installed as a winter extension so its skills, agents, and `on_env_init` / `on_env_destroy` hooks are wired into the workspace itself.

## Getting started

1. Clone this repo.
2. Install the winter CLI (`./tools/winter-cli/install.sh`) and run `winter ws init` to clone the project repos.
3. Start working in `alpha/`. Each project repo is a worktree on branch `alpha`.

See `CLAUDE.md` for workspace conventions and `context/project/contributing.md` for delivery rules.

## Running winter from a feature worktree

The installed `winter` script normally runs the CLI checked into `tools/winter-cli/` at the workspace root (i.e. master). To exercise an in-flight CLI change living in a feature worktree without reinstalling, prefix the command with `--winter=PATH`:

```sh
# from anywhere inside the workspace:
winter --winter=./alpha/winter dashboard
winter --winter=./alpha/winter ws status alpha
```

`PATH` is the feature worktree's checkout of the `winter` repo (the directory containing `tools/winter-cli/`). The launcher swaps the source tree but keeps the workspace root, config, and standalone extensions exactly the same — only the Python code that runs is different.

`--winter=` must be the **first** argument; everything after it is forwarded to the alpha CLI verbatim.

First time you point at a new worktree, `mise trust <PATH>/tools/winter-cli/mise.toml` so mise will load its tool versions.

Visual plugins shipped from a feature worktree (e.g. `alpha/winter-service-tmux/plugin.py`) are picked up by the dashboard only after they land in the workspace's installed extension directory at `.winter/ext/<ext>/`. To preview a plugin during development, symlink it:

```sh
ln -sfn ../../alpha/winter-service-tmux/plugin.py .winter/ext/service-tmux/plugin.py
```

then remove the symlink once the change is merged and reinstalled.

## What this is *not*

This repo isn't the winter framework. The framework lives in `winter-workspace` (cloned upstream remote: `winter`). This repo just uses winter to develop winter — every change to the framework or its extensions flows through a feature worktree here.
