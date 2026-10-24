# Harness runtime-port availability

Which agent harnesses in this workspace support the semantic runtime ports declared in
`winter-workflow:/methodology/runtime-ports.md` — the per-harness capability facts a session adapter resolves before
choosing an execution placement that depends on a port. A harness, or a nesting depth, with no declared support for a
port is treated as **not** supporting it: degrade per the process's declared fallback, or return
`unsupported-capability` when no fallback is permitted.

| Harness     | Spawn an isolated role                                                                                           | Fork the current context                                                                                                                                                                                                                                                                                                       | Create and coordinate resident workers                                                                                                                                                                                                                                                               |
| ----------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Code | Available at every nesting depth that carries the `Agent` tool — the main session loop and subagents granted it. | **Main session loop only**: the `Agent` tool with `subagent_type: "fork"` copies the session's accumulated context into each concurrent child. A spawned subagent's `Agent` tool creates fresh isolated agents only — it cannot fork its own context, so an isolated role is never fork-capable regardless of its tool grants. | Available to a context holding both `Agent` and `SendMessage`: `Agent` starts the worker, `SendMessage` re-addresses it by id or name with its context intact, `ListAgents` enumerates live workers. A worker retains everything from its prior rounds; the coordinating context owns its lifecycle. |

No other harness in this workspace currently declares fork or resident-worker support; treat their contexts as
spawn-only.

The placement consequence, stated once: a process step that requires a fork-capable seat can hold in a Claude Code
**main-loop** context, and can never hold inside a spawned subagent — a process wanting both isolation and fork from one
context must use a main-loop context that is already isolated by circumstance (e.g. a fresh session), or accept its
declared fallback.

A resident worker's seat is the coordinating context, not the worker: a context that can spawn but cannot re-address —
no `SendMessage`, or a harness with no declared support above — cannot hold a step that requires residency. Residency
also carries no isolation guarantee across rounds. A worker re-addressed after an earlier round retains that round, so a
process whose step depends on the worker being cold must spawn a new isolated role for it rather than reusing a resident
one.
