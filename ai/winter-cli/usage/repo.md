# `winter repo` — repository commands

Manage the repositories declared in the workspace config. For the hub and the rest of the command surface, see [../index.md](../index.md).

| Command | Usage | Purpose |
|---------|-------|---------|
| `winter repo list` | `winter repo list [--json]` | List all project and standalone repositories and their types |
| `winter repo add` | `winter repo add URL [--standalone] [--name N] [--main-branch B] [--git-exclude E] [--cmd C] [--pinned] [--path P] [--prefix P] [--local] [--json]` | Add a repository to the workspace config (writes `.winter/config.toml` unless `--local` writes `.winter/config.local.toml`) |
| `winter repo remove` | `winter repo remove <project\|standalone>/NAME [--local] [--json]` | Remove a repository entry from the config |

For the `.winter/config.toml` repository schema these commands read and write, see [setup.md](../setup.md).
