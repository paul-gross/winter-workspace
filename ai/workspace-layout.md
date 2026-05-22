# Workspace Layout (Polyrepo)

This workspace manages **multiple project repositories** as peers. All repos are treated equally.

## Directory Structure

```
./                              workspace branch - this is where you are
├── CLAUDE.md                   # Workspace instructions
├── CLAUDE.winter.md            # Installed-extension block (@-imported from CLAUDE.md)
├── ai/                         # Workspace documentation
│   ├── workspace-layout.md     # This file
│   ├── worktree-ops.md         # Git commands for this topology
│   ├── winter-cli/             # CLI command reference + setup guide
│   ├── setup-project-setup.md  # Walkthrough for authoring project-setup.md
│   ├── contributing-setup.md   # Walkthrough for authoring contributing.md
│   └── project/                # Project-specific integration config (contributing.md, workflow.sh)
├── .claude/                    # Workspace-level agents, skills, and settings
│   ├── agents/                 # Top-level .md files plus <prefix>-* symlinks from extensions
│   └── skills/                 # Top-level skill dirs plus <prefix>-* symlinks from extensions
├── .winter/                    # Workspace-level winter config and installed extensions
│   ├── config.toml             # Repo declarations (project + standalone)
│   ├── config.local.toml       # Optional local override (gitignored)
│   └── ext/<short-name>/       # Standalone clones for installed extensions
├── tools/                      # Workspace tooling
│   └── winter-cli/             # The `winter` CLI source
├── projects/                   # All project repositories (source checkouts)
│   ├── <repo-1>/               # Project repo (main branch)
│   ├── <repo-2>/               # Project repo (main branch)
│   └── <repo-n>/               # Project repo (main branch)
├── <standalone-repo>/          # Standalone repos cloned at workspace root (when no path override; see Repo Inventory)
├── up / down / status          # Symlinked into every feature env by winter-service-tmux
└── {greek-letter}/             # Feature environment directories
    ├── <repo-1>/               # Worktree of project repo (feature branch)
    ├── <repo-2>/               # Worktree of project repo (feature branch)
    ├── <repo-n>/               # Worktree of project repo (feature branch)
    ├── up / down / status      # Symlinks to the extension scripts above (running services from the env dir)
    └── .winter.env             # Per-environment shell env file (WINTER_ENV, WINTER_PORT_BASE, project-specific vars)
```

## Source Checkouts

The following directories are source checkouts — **never work in these directly**:
- `./projects/<name>/` — main branch checkouts for each repo

All development happens in feature worktrees (e.g., `./alpha/<repo-name>/`).

## Feature Worktree Structure

Each Greek letter directory (e.g., `alpha/`) contains a git worktree for **every** repository in `projects/`. All worktrees within a feature directory share the same branch name (the Greek letter).

When working on a feature in `alpha/`:
- Repo code is at `./alpha/<repo-name>/`
- Environment shell vars are at `./alpha/.winter.env` — `WINTER_ENV`, `WINTER_ENV_INDEX`, and `WINTER_PORT_BASE` are seeded by `winter ws init`; project-specific vars (per-service ports, database URLs, etc.) are appended below the managed block by `project-setup.md`.

## Repo Inventory

The authoritative repo lists live in `workspace:/.winter/config.toml`:

- `[[project_repository]]` — repos that get cloned into `./projects/` and worktreed into Greek-letter feature directories.
- `[[standalone_repository]]` — repos cloned at the workspace root (or under a configured relative `path`), skipped during feature branching. Used for winter extensions and any auxiliary repo that shouldn't be multiplied per-feature.

Each entry declares the repo's name, clone URL, git-exclude entries, and setup commands. Project entries also carry an optional main branch (falls back to the top-level `main_branch`) and pinned status. Standalone entries can additionally declare a `prefix` override for the extension symlink prefix.

The directories under `./projects/` and the standalone directories at the workspace root are a materialization of that config — `winter ws init` brings them into alignment. To list the declared repos:

```bash
winter repo list
```
