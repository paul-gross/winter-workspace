# CLAUDE.md - Workspace Management

We are working in a **multi-worktree, multi-repository** development workspace, optimized for agentic development. Multiple project repositories are cloned here, and all feature development happens in feature environments comprised of multiple project-specific worktrees — not in the source checkouts. Multiple agents can work in parallel across different feature environments without interfering with each other.

This workspace is powered by **winter**, a framework that manages the worktrees, service orchestration, and agent tooling. The project repos know nothing about winter — all workspace configuration lives here in the workspace itself.

Read [ai/workspace-layout.md](./ai/workspace-layout.md) to understand the directory layout, which directories are source checkouts (never edit directly), and how feature worktrees relate to the project repos.

@ai/project/index.md

## Feature environments and Greek letters

Feature environments are named after Greek letters: `alpha/`, `beta/`, `gamma/`, etc. Each env contains a feature worktree for every project repository, all on a branch matching the env name. For example, `./alpha/my-app/` is a worktree of `my-app` on branch `alpha`.

Each env has an index used to assign unique ports per env. Ports start at **4000** and each index adds **+100**: alpha (1) → 4100, beta (2) → 4200, gamma (3) → 4300, and so on. This ensures multiple envs can run services simultaneously without port conflicts.

Greek letters have fixed indices 1..24. For non-Greek env names (arbitrary feature branches), get the deterministic hashed index with:

```bash
winter ws index <name>
```

Default to **alpha**. Use **beta** if alpha is occupied. Only create additional envs when needed, and confirm with the user first.

Full alphabet: alpha, beta, gamma, delta, epsilon, zeta, eta, theta, iota, kappa, lambda, mu, nu, xi, omicron, pi, rho, sigma, tau, upsilon, phi, chi, psi, omega

## Winter CLI

The `winter` command manages feature environments and repositories across the workspace. Use it instead of manual multi-repo git operations. Use raw git for single-repo work (staging, committing, conflict resolution).

@ai/winter-cli/index.md

## Creating a new feature environment

Only needed when existing envs are all occupied. Run:

```bash
winter ws init <name>
```

This creates the env directory, per-repo `git worktree` on a branch named `<name>`, copies git identity, writes git-exclude entries, runs each repo's `cmd` list, seeds the env's `.winter.env` with `WINTER_ENV`/`WINTER_ENV_INDEX`/`WINTER_PORT_BASE`, and runs each installed winter extension's `on_env_init` hook. After it finishes, follow `workspace:/ai/project/project-setup.md` for any project-specific orchestration that isn't declared in the config (e.g. appending project-specific vars to `.winter.env`, provisioning per-environment databases, generating other env files).

## Path Notation

Paths use a `<context>:<path>` prefix to clarify which repo/branch a file lives in:
- `workspace:` — the workspace root (this repo's workspace branch)
- `<env>:` — a feature environment (e.g., `alpha:` resolves to a per-repo worktree inside `alpha/`)
- `<extension-name>:` — a winter extension (e.g., `winter-product:`)

## Key References

| Topic | Location |
|-------|----------|
| Directory layout and repo topology | [ai/workspace-layout.md](./ai/workspace-layout.md) |
| Winter CLI command reference | [ai/winter-cli/index.md](./ai/winter-cli/index.md) |
| Worktree git operations (create, sync, complete) | [ai/worktree-ops.md](./ai/worktree-ops.md) |
| Contributing conventions (merge, push, delivery) | [ai/project/contributing.md](./ai/project/contributing.md) |
| Installed winter extensions | `CLAUDE.winter.md` |

## Rules

1. **Never work in source checkouts directly** — use feature environments for all code changes (see `ai/workspace-layout.md` for which directories are source checkouts)
2. **Local branch = Greek letter, remote branch = feature name** — each env's worktrees use a Greek-letter branch locally (e.g., `alpha`). The remote feature branch (e.g., `feature/basic-addon`) is a separate name configured via tracking. See [ai/worktree-ops.md](./ai/worktree-ops.md) for how to connect an env to a remote feature branch.
3. **Confirm before working** — always verify which env to work in
4. **Always spawn subagents from the workspace root** — subagents and teammates must be created while the working directory is the workspace root. Spawning from a project subdirectory causes the subagent to lose workspace context including this CLAUDE.md, agent definitions, and skills.
5. **Follow the project's contributing conventions when completing work** — see [ai/project/contributing.md](./ai/project/contributing.md). If that file doesn't exist, guide the user to establish one documenting how completed work should be merged, pushed, and delivered for their specific projects.

# Winter Extensions

@CLAUDE.winter.md

# Local Settings

@CLAUDE.local.md
