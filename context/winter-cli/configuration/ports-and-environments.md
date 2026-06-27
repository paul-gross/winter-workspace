# Ports & environments

Winter assigns each feature environment a port band derived from its index, and computes per-env derived variables at runtime. These keys live in `.winter/config.toml`.

## Port allocation

```toml
# Port allocation — all four keys are optional; shown here with their defaults.
base_port = 4000          # start of this workspace's port band; set a different value to separate co-located workspaces
ports_per_env = 20        # ports per feature env; per-env base = base_port + index * ports_per_env
env_aliases = [           # fixed-index env names (1..N); aliases get stable slots, all other names hash into the remainder
  "alpha", "beta", "gamma", "delta", "epsilon",
  "zeta", "eta", "theta", "iota", "kappa",
]
envs_per_workspace = 48   # max feature-env index (1..envs_per_workspace); must be >= len(env_aliases) + 2
```

## Env var bands

Two scope-bound bands of config-driven variables can be declared in `.winter/config.toml`. Values support `${...}` substitution; literal text passes through unchanged. These variables are computed at runtime by `EnvProvisionerService` and injected into every provider subprocess by `winter service`. To inspect the computed values for a scope, use `winter env <scope>` (see [usage/env.md](../usage/env.md)).

```toml
[env.workspace.vars]
SHARED_DB_PORT = "${WINTER_WORKSPACE_PORT_BASE+10}"   # shared workspace service

[env.feature.vars]
WTS_WEB_PORT = "${WINTER_PORT_BASE+10}"
WTS_API_PORT = "${WINTER_PORT_BASE+11}"
WTS_DB_PORT  = "${WINTER_PORT_BASE+12}"
DATABASE_URL = "postgresql://wts:wts@localhost:${WTS_DB_PORT}/wts-${WINTER_ENV}"  # reuses WTS_DB_PORT and WINTER_ENV
```

**Workspace band (`[env.workspace.vars]`)** — rendered for both the `workspace` scope and every feature env. Because `WINTER_PORT_BASE` is omitted from the workspace scope, workspace-band entries that reference a port should use `${WINTER_WORKSPACE_PORT_BASE+N}`.

**Feature band (`[env.feature.vars]`)** — rendered only for feature envs; never emitted for the `workspace` scope.

**Resolution per scope:**

| Scope | Variables emitted |
|-------|-----------------|
| `workspace` | `WINTER_ENV`, `WINTER_ENV_INDEX`, `WINTER_WORKSPACE_PORT_BASE` + workspace-band entries only |
| `<feature>` | `WINTER_ENV`, `WINTER_ENV_INDEX`, `WINTER_PORT_BASE`, `WINTER_WORKSPACE_PORT_BASE` + workspace band rendered first, then feature band on top (feature band wins key collisions) |

A feature-band entry may reference keys already rendered from the workspace band.

**Migration from `[env.vars]` (hard break).** A config that still declares the legacy `[env.vars]` table is rejected with a `ConfigError` at startup. Migrate by moving entries to `[env.feature.vars]` (for feature-env variables) or `[env.workspace.vars]` (for shared workspace variables). There is no alias or fallback — the failure is intentional so no variables are silently dropped.

**Token grammar.** Two forms are supported:

- `${NAME}` — substitutes the string value of `NAME`.
- `${NAME+N}` — adds a non-negative integer `N` to `NAME` (which must parse as an integer).

`NAME` resolves against an **accumulating scope**: seeded with the base vars available for the scope (see table above) and grown by each rendered band entry **in TOML declaration order** — so a later entry can reuse an earlier one (as `DATABASE_URL` reuses `WTS_DB_PORT` above). `WINTER_PORT_BASE` is not special: `${WINTER_PORT_BASE+N}` is just the base-var case.

Resolution is computed at dispatch time by `EnvProvisionerService` — concrete values are injected into the subprocess environment. An undefined name, `+N` applied to a non-integer value, or any other malformed `${...}` token is a fatal error surfaced when the command runs.

## Index reservation

The env name → index mapping itself is recorded in [`.winter/state.toml`](./config-files.md#state-registry). Two indices are reserved and never assigned to a regular feature env:

Index 0 (`base_port`..`base_port+ports_per_env-1`) is reserved for a future single-slot "local" environment — a pre-seeded shared dataset/area distinct in purpose from the regular alias and hash-band slots. It is never assigned. The slot immediately after the aliases (`N+1`, default index 11 with the 10-alias default) is reserved as a buffer between the fixed alias band and the hash band; this is why the invariant requires `envs_per_workspace >= len(env_aliases) + 2` (not `+1`).
