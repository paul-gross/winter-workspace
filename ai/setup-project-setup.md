# Guide: Creating project-setup.md

## What it is

`workspace:/ai/project/project-setup.md` is a reproducible recipe for initializing any new feature environment. When an agent creates a new feature environment (e.g., `gamma/`), it follows `workspace:/ai/project/project-setup.md` to create environment files, set up databases, seed data, and do whatever else `winter ws init` doesn't already cover.

## Why it exists

Each feature environment is independent — its own checkout, its own dependencies, its own ports and databases — intended to run in parallel with other feature environments on the same machine. Each environment gets a port window from its index (workspace base seeds `WINTER_PORT_BASE` in the per-environment `.winter.env`); a service orchestration extension like `winter-service-tmux` runs services that consume those vars. This is what allows multiple agents to work on different features simultaneously without interfering with each other. Without setup instructions, agents have to guess how to get things running — or ask the user every time. This file makes environment initialization fast, repeatable, and autonomous.

## Division of responsibility: config vs. project-setup.md

`winter ws init <letter>` already handles the parts that are uniform across environments:

- Cloning each repo from `[[project_repository]].url`
- Cloning standalone repos declared in `[[standalone_repository]]` and processing winter extensions
- Creating per-repo `git worktree`s on a branch matching the worktree name
- Stamping git identity from `.winter/config.local.toml`
- Writing `git_excludes` (workspace-wide and per-repo) into each repo's `.git/info/exclude`
- Running each repo's `cmd` list (`npm install`, `dotnet restore`, etc.)
- Running every installed extension's `on_env_init` hook

The goal here is **not** to replace `project-setup.md`. It's to offload the boring, standard pieces — single-line installs, a handful of file patterns to git-ignore — into `.winter/config.toml` so the cli can run them automatically. Anything that's conditional, multi-step, depends on the environment's ports/db/env, or needs branching logic stays in `project-setup.md` where it can be expressed clearly.

Rule of thumb:
- **Goes in config:** would fit on one line in a README's "Getting Started" section.
- **Stays in project-setup.md:** anything you'd describe with "first do X, then if Y…" or that references `<letter>`/`<index>`.

## How to create it with the user

Offer the user two approaches: *"I can research your codebase and figure out the setup requirements automatically, or you can walk me through it. Which do you prefer?"*

**If researching automatically:** Spawn an Opus subagent to explore the project repos. The subagent searches for package managers, dockerfiles, docker-compose files, env templates (`.env.example`, `.env.sample`), migration scripts, README setup sections, and existing documentation. Using a subagent keeps the research out of the main setup context — we only care about the findings. The subagent reports back a structured summary of what it found, and you present those findings to the user for confirmation before writing.

**If the user prefers a guided approach**, walk through each area below with focused questions.

Either way, synthesize the answers — some go into `.winter/config.toml`, some go into `ai/project/project-setup.md`.

### 1. Dependencies → `[[project_repository]].cmd` in `.winter/config.toml`

Ask: *"How are dependencies installed for each repo? (e.g., `npm install`, `pip install -r requirements.txt`, `cargo build`)"*

If the answer is a single, unconditional command, write it to that repo's `cmd` list:

```toml
[[project_repository]]
name = "my-app"
url = "..."
cmd = ["pnpm install"]
```

If the install needs branching, env-dependent decisions, or post-install steps that read environment state, **leave `cmd` empty** and document the install in `project-setup.md` instead. The cli is a shortcut for the easy 90%, not a workflow engine.

### 2. Environment files → mostly `project-setup.md`, generated artifacts → `git_excludes`

Ask: *"Does the project need environment files (e.g., `.env`)? What variables are required?"*

Probe for:
- Base ports for each service (web server, API, database, etc.)
- How ports should be offset per environment (alpha=+1, beta=+2, etc.)
- Database connection strings — do they need per-environment database names?
- API keys or secrets — can they be shared across environments or do they need to be unique?
- Any other per-environment config (Redis prefix, S3 bucket, etc.)

The env-file *generation logic* (heredocs that write per-environment values into env files) goes into `project-setup.md` as numbered steps.

#### `.winter.env` — append, don't overwrite

`winter ws init <name>` seeds `<name>/.winter.env` with `WINTER_ENV`, `WINTER_ENV_INDEX`, and `WINTER_PORT_BASE`, bracketed in a managed block at the top:

```
# >>> winter (managed) — base environment variables; do not edit by hand
WINTER_ENV=alpha
WINTER_ENV_INDEX=1
WINTER_PORT_BASE=4100
# <<< winter (managed) — project-specific variables go below this marker
```

Project-specific variables go *below* the closing marker. The shape for `project-setup.md` is an `>>` (append) heredoc that derives values from the seeded vars:

```bash
# Run from the worktree root after `winter ws init <name>`:
source .winter.env
cat >> .winter.env <<EOF

BACKEND_PORT=$((WINTER_PORT_BASE + 0))
FRONTEND_PORT=$((WINTER_PORT_BASE + 1))
DATABASE_URL=postgres://localhost/myapp_$WINTER_ENV
EOF
```

Two patterns for port offsets:
- **Worktree base + service offset:** `BACKEND_PORT=$((WINTER_PORT_BASE + 0))`, `FRONTEND_PORT=$((WINTER_PORT_BASE + 1))` — every environment gets a 100-port window starting at its base. Default this when the project doesn't already have a port table.
- **Service base + index:** `BACKEND_PORT=$((4200 + WINTER_ENV_INDEX))` — backend runs on 4201/4202/4203 in alpha/beta/gamma. Use this when the project pre-assigns service slots.

Never `>` (overwrite) `.winter.env` — that clobbers the managed block. Always `>>`.

#### Other env files

For `.env`, `.env.development.local`, `.env.production`, etc., generate them with full `>` heredocs (or whatever tool the project provides). Those aren't shared with `winter ws init`, so they can be rewritten freely.

The *generated file paths* go into `.winter/config.toml` as `git_excludes` so they're never committed:

```toml
# Workspace-wide (every repo gets these excludes)
git_excludes = ["*.local.*", "*.generated.*"]

[[project_repository]]
name = "frontend"
git_excludes = [".env.development.local"]   # only this repo
```

### 3. Databases → `project-setup.md`

Ask: *"Does the project use databases? How are they created and migrated?"*

Probe for:
- Database engine (Postgres, MySQL, SQLite, etc.)
- Does each environment need its own database? (Usually yes — e.g., `myapp_alpha`, `myapp_beta`)
- Migration commands
- Whether the database server is shared or per-environment

These steps belong in `project-setup.md` — they're per-environment orchestration, not declarative repo config.

### 4. Build steps → usually `project-setup.md`

Ask: *"Are there any build or codegen steps needed before the project can run? (e.g., `npm run build`, code generation, compiling protos)"*

Default to `project-setup.md`. Only append a build step to a repo's `cmd` list if it's a single command with no dependencies on env files, ports, or the environment's database — same rule as section 1.

### 5. Seed data → `project-setup.md`

Ask: *"Does the project need seed data or initial state to be useful? (e.g., fixtures, migrations with default data, creating admin users)"*

Always per-environment — goes in `project-setup.md`.

### 6. Verification → `project-setup.md`

Ask: *"How can we verify that setup worked? Is there a health check, test suite, or command that confirms things are ready?"*

Final step of `project-setup.md`.

### 7. Pinned repos → `[[project_repository]].pinned`

Ask: *"Are any of these repos shared tooling that should always track `origin/main` instead of being branched per-feature? (e.g., a CLI tool, mock services)"*

For each one, set `pinned = true` on its `[[project_repository]]` entry. `winter ws init <letter>` skips feature branching for pinned repos and just keeps them on the main branch.

### Output

Two artifacts:

1. **`.winter/config.toml`** — enriched with simple, unconditional `cmd` entries, plain-pattern `git_excludes`, and `pinned` flags on the `[[project_repository]]` entries that ws-setup created. Keep it boring; if in doubt, leave it out.
2. **`workspace:/ai/project/project-setup.md`** — numbered steps for everything else: complex installs, env file generation with port offsets, database creation/migration, seed data, post-init build steps, verification. Use variables like `<letter>` and `<index>` where environment-specific values are needed, and explain how to derive them. This file is still where the real setup lives.

This guide stops at writing the artifacts. Applying the changes to existing environments and running the setup against an environment is the caller's responsibility (see the ws-setup skill).
