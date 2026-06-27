# `winter env` — print the runtime environment for a scope

```
winter env <scope>
```

Print the complete runtime environment for *scope* as sourceable `export KEY=value` lines, one per variable, in the order the provisioner returns them:

```
export WINTER_ENV=alpha
export WINTER_ENV_INDEX=1
export WINTER_PORT_BASE=4060
export WINTER_WORKSPACE_PORT_BASE=4000
export MY_APP_PORT=4061
```

*scope* is either a feature-env name (e.g. `alpha`, `beta`) or the reserved word `workspace` for the workspace-level singleton scope.

## Usage

**Source into the current shell:**

```bash
source <(winter env alpha)
```

**Source in a script or Dockerfile:**

```bash
eval "$(winter env alpha)"
```

**Inspect the environment for a scope:**

```bash
winter env alpha          # feature env
winter env workspace      # workspace singleton scope
```

## Variables printed

The exact set depends on the scope:

**`winter env workspace`** emits only the workspace trio plus any `[env.workspace.vars]` entries:

| Variable | Meaning |
|----------|---------|
| `WINTER_ENV` | `workspace` |
| `WINTER_ENV_INDEX` | `0` |
| `WINTER_WORKSPACE_PORT_BASE` | Port-band start for index 0 |

`WINTER_PORT_BASE` is NOT emitted for the workspace scope.

**`winter env <feature>`** emits the full feature set:

| Variable | Meaning |
|----------|---------|
| `WINTER_ENV` | Scope name (e.g. `alpha`) |
| `WINTER_ENV_INDEX` | Stable index used for port allocation |
| `WINTER_PORT_BASE` | Port-band start for this scope (`base_port + index * ports_per_env`) |
| `WINTER_WORKSPACE_PORT_BASE` | Port-band start for index 0 (the workspace port base) |

Followed by the band entries from `.winter/config.toml`: workspace scope shows only the workspace band (`[env.workspace.vars]`); feature scope shows both bands with the feature band (`[env.feature.vars]`) overlaid on top. See [ports-and-environments.md](../configuration/ports-and-environments.md#env-var-bands) for band ordering, collision rules, and token grammar.

## Exit codes

| Exit code | Meaning |
|-----------|---------|
| 0 | Success — every line written to stdout. |
| 1 | Scope unknown or env-vars template error — message on stderr, no output. |

## Notes

- Output is shell-safe: values are quoted with `shlex.quote` so special characters do not break the `source`/`eval` recipe.
- `winter env` is the canonical way to load an env's variables into a shell. Services run by `winter service up` receive the same variable set injected directly into the provider subprocess environment — no file sourcing needed.
