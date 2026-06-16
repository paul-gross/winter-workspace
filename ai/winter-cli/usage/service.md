# `winter service` — service orchestration

For the hub and the rest of the command surface, see [../index.md](../index.md).

```bash
winter service up alpha                # start env alpha's services
winter service down alpha              # stop them
winter service status alpha            # report service status
winter service restart alpha backend   # bounce one service (WINTER_SERVICE_NAME conveyed as env var)
winter service logs alpha              # stream all services' logs
winter service logs alpha api          # stream logs for the `api` service only
winter service logs alpha -f           # stream until Ctrl-C (exit 130)
winter service logs alpha -n 50        # last 50 lines (default: 200)
winter service logs alpha --since=5m   # since 5 minutes ago (normalized to RFC3339)
winter service logs alpha --since=2026-06-13T10:00:00Z  # since absolute timestamp
winter service logs alpha -t           # prefix each line with its timestamp
```

`winter service` owns a stable `up`/`down`/`status`/`restart`/`logs` interface and dispatches each invocation to whichever orchestrator the workspace registers. Consumers depend on `winter service …` and never on the orchestrator's implementation, so a workspace can swap tmux for containers or a supervising daemon without re-teaching agents, docs, or habits.

Registering an orchestrator uses the capability registry: `capabilities.service = "<name>"` in the `[capabilities]` table of `.winter/config.toml` names the extension, and `provides.service = "<path>"` in that extension's `[provides]` table in `winter-ext.toml` declares the entrypoint. When exactly one extension provides the slot, the `capabilities.service` binding is optional (implicit sole-provider). Two providers with no explicit binding is an ambiguity error. The legacy keys `service_orchestrator` (config) and `orchestrate_services` (manifest) are still accepted as **deprecated** aliases — config-load folds `service_orchestrator` into `capabilities.service`; `capability_entrypoint()` falls back to `orchestrate_services` when `provides.service` is absent. See [setup.md#capability-registry](../setup.md#capability-registry) for the full resolution model and [capabilities.md](./capabilities.md) to introspect the current binding.

## Local-path override

Use the `--service-orchestrator` root flag or the `WINTER_SERVICE_ORCHESTRATOR` environment variable to point `winter service` at a **local extension directory** for a single invocation — without changing `.winter/config.toml` or reinstalling anything. This is the primary way to test an in-progress orchestrator whose installed copy still lags the worktree:

```bash
# flag form (highest precedence)
winter --service-orchestrator=alpha/winter-service-tmux service up alpha

# env-var form
WINTER_SERVICE_ORCHESTRATOR=alpha/winter-service-tmux winter service status alpha
```

**Precedence (highest wins):** `--service-orchestrator` flag → `WINTER_SERVICE_ORCHESTRATOR` env var → `service_orchestrator` in `.winter/config.toml`.

**Path-vs-name disambiguation:**
- If the value contains an OS path separator (`/` on POSIX) or resolves to an existing directory → **path mode**: reads `winter-ext.toml` from that directory directly, skipping the config-key-present and matches-an-installed-extension checks. The directory must still declare a `service` entrypoint (`provides.service`, or the legacy `orchestrate_services`) in its `winter-ext.toml`, and that entrypoint file must exist on disk.
- Otherwise (bare name like `winter-service-tmux`) → **name mode**: falls through to the normal registered-extension lookup, same as the config key.

**Doctor note:** `winter doctor` reflects the *installed* extension (not the override target), so during an override window, warnings about a lagging or mismatched installed extension are expected and can be ignored.

**Scope:** the override affects **dispatch only** — `WINTER_EXT_DIR`/`WINTER_EXT_PREFIX` are set from the resolved local directory, and the entrypoint is invoked from it. It does NOT affect `winter-service-tmux:` path-notation used in agent docs, nor `@`-loaded markdown references. The override is per-invocation only; it is not persisted.

**Typical use:** during orchestrator development, when the workspace's installed extension copy is behind your working branch:

```bash
# All four verbs work via the override:
winter --service-orchestrator=alpha/winter-service-tmux service up alpha
winter --service-orchestrator=alpha/winter-service-tmux service status alpha
winter --service-orchestrator=alpha/winter-service-tmux service down alpha

# Control: without the override, the installed (lagging) copy is used — expect
# "declares no service entrypoint" or "not an installed extension" if it hasn't shipped yet.
winter service up alpha
```

## Orchestrator contract

This is the full spec a service-orchestrator extension is written against — conform to it without reading winter's source.

### Uniform invocation rule

winter always invokes the entrypoint as exactly:

```
<entrypoint> <action> <env>
```

`<action>` is one of `up`, `down`, `status`, `restart`, `logs`; `<env>` is the feature-env name (`alpha`, `beta`, …). **No raw user tokens ever reach the entrypoint argv** — all action-specific parameters are conveyed via `WINTER_*` environment variables (see below). An implementation **must accept all five action words** even if only to refuse one it does not implement: for an unsupported action it should exit non-zero with a message, which winter passes through.

### Always-present environment variables

Every dispatch — regardless of action — sets these three variables and runs the entrypoint with **cwd at the workspace root**:

| Var | Meaning |
|-----|---------|
| `WINTER_WORKSPACE_DIR` | Absolute path to the workspace root. |
| `WINTER_EXT_DIR` | Absolute path to this orchestrator extension's clone (the dir containing `winter-ext.toml`). |
| `WINTER_EXT_PREFIX` | The resolved symlink prefix for this extension. |

These three are winter's shared extension-subprocess context, defined for the hook/doctor/lint dispatches in [setup.md](../setup.md#hook-env-var-contract); `winter service` provides them identically. Working directory varies by surface: `winter service`, `doctor`, `lint`, and the `on_workspace_reconcile` hook run at the workspace root, while the `on_env_*` hooks run at the env root.

### Per-action environment variables

These are layered on top of the always-present set above, scoped to the action that needs them:

| Action | Env var | Value |
|--------|---------|-------|
| `restart` | `WINTER_SERVICE_NAME` | The service name to bounce (always set; never empty). |
| `logs` | `WINTER_LOG_SERVICES` | Space-joined service names to include; empty string = all. |
| `logs` | `WINTER_LOG_FOLLOW` | `1` = stream live, `0` = emit backlog and exit. |
| `logs` | `WINTER_LOG_TAIL` | Positive integer or `all`. The orchestrator SHOULD honour this; winter applies a backstop. |
| `logs` | `WINTER_LOG_SINCE` | RFC3339 absolute timestamp (pre-normalised from any duration); empty if unset. |
| `logs` | `WINTER_LOG_UNTIL` | RFC3339 absolute timestamp; empty if unset. |
| `logs` | `WINTER_LOG_TIMESTAMPS` | `1` = per-line timestamps requested; `0` = not requested. |

For `up`, `down`, and `status` no action-specific env vars are set beyond the always-present set above.

### Wire contract (orchestrator stdout → winter) — `logs` only

The orchestrator's stdout for `logs` must be **NDJSON**, one event per line:

```json
{"ts":"2026-06-13T10:00:01Z","svc":"api","msg":"listening"}
{"svc":"worker","msg":"processing job 42"}
```

Fields:
- `svc` (required) — the originating service name.
- `msg` (required) — the log message.
- `ts` (optional) — RFC3339 timestamp; omit when the backend has no per-line timestamps (e.g. `tmux capture-pane`).

The orchestrator's **stderr must reach winter's stderr** (diagnostics), NOT be merged into the NDJSON stdout. The orchestrator MAY pre-filter by `WINTER_LOG_SINCE`/`UNTIL`/`FOLLOW`/`TAIL` server-side for efficiency; winter applies idempotent backstops regardless.

### Render contract (winter stdout → user/pipe)

Winter parses the NDJSON and writes plain lines to its own stdout: `[<ts> ][<svc> | ]<msg>`.

- Prefix `<svc> | ` **only when ≥2 services are in scope** — i.e., when the user requests multiple services or all services (empty `SERVICE...`). A single explicit service → no prefix.
- Under `-t`/`--timestamps`, prepend the RFC3339 timestamp; lines without a `ts` field are rendered without a timestamp prefix (with one stderr warning emitted).
- Lines that are not valid JSON are treated leniently: the whole raw line becomes `msg` with no `svc` or `ts`.
- winter's own warnings and diagnostics go to stderr. This plain-line stdout is what makes `winter service logs alpha | grep ERROR | less` portable across orchestrators.

### Idempotent backstop filters (winter-side)

Winter applies these backstops even when the orchestrator has pre-filtered, ensuring the user-facing contract holds regardless of orchestrator quality:

- **Service filter:** if explicit services requested and a line's `svc` is not in the set, drop it. Lines without a `svc` field are also dropped when a filter is active.
- **Time filter (`--since`/`--until`):** applied per-line only to lines that have a parseable `ts`. The boundary is **inclusive**: a line whose `ts` exactly equals the `--since` or `--until` threshold is kept. Lines without `ts` are always kept (winter cannot time-filter them). If `--since`/`--until` was requested AND at least one line lacked a `ts`, winter emits one stderr warning that the time filter is partial.
- **Timestamps (`-t`):** if requested but a line has no `ts`, the timestamp prefix is omitted for that line; winter emits one stderr warning.
- **Tail backstop:** in **non-follow** mode, winter keeps a ring buffer (last N lines) and emits only those after the stream ends. In **follow** mode (`-f`), winter does NOT re-tail — it relays lines live and relies on the orchestrator having honoured `WINTER_LOG_TAIL`. This is an intentional limitation: winter cannot distinguish backlog from live output during a follow session.

### Exit codes

- Click owns flag-parse errors: exit 2 (before dispatch).
- The orchestrator's exit code becomes `winter`'s exit code.
- `-f` interrupted by Ctrl-C: exit 130 (and the child receives the signal naturally).
