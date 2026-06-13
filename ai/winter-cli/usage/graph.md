# `winter graph` — module dependency graph

For the hub and the rest of the command surface, see [../index.md](../index.md).

```bash
winter graph            # human-readable `module → deps` listing
winter graph --json     # {module: [requires...]} adjacency map
```

Prints the module dependency graph. Every installed module that ships a `winter-ext.toml` becomes a node; its `requires` list becomes its edges. `--json` emits a `{module: [requires...]}` adjacency map keyed by module name.

It is a read-only data command with a stable JSON contract, meant for humans and tooling alike. In particular, lint checks consume it via `$WINTER_CLI graph --json` (the lint dispatcher hands every check the `WINTER_CLI` path) so they can reason about dependencies without re-parsing every manifest — e.g. the module-extractability check. A lint check may call `winter graph`, but must never call `winter lint` (which would recurse).
