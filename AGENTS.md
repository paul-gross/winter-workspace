# Winter workspace

We are working in a multi-repository, multi-worktree development workspace: several project repositories are cloned into
it, and the **winter** framework manages its worktrees, service orchestration, and agent tooling. All feature
development happens in feature environments, each composed of per-project worktrees — never in the source checkouts — so
multiple agents can work in parallel in different feature environments without interfering with one another. The project
repositories carry no knowledge of winter; every piece of workspace configuration lives in the workspace itself.

Each of the following files declares fundamental pieces pertinent to every task and is imported eagerly:

- IMPORTANT: @context/project/index.md — workspace-owned project context
- IMPORTANT: @AGENTS.winter.md — the winter-generated declaration of installed winter extensions
- IMPORTANT: @AGENTS.local.md — the workspace's local settings

## Winter CLI

The `winter` command manages worktrees and repositories across the whole workspace. Multi-repo operations — init,
status, fetch, pull, connect, push, diff — go through it; single-repo work — staging, committing, resolving conflicts,
interactive rebase — uses raw git.

## Feature-environment lifecycle

Bring a feature environment up in order: `winter ws init <env>`, then `winter provision <env>`, then
`winter service up <env>`. Never run or exercise an environment that has not been provisioned — provisioning is a
required baseline operation, not an optional step.
[context/environment-lifecycle.md](./context/environment-lifecycle.md) owns the lifecycle phases and the
provision-before-run baseline rule.

## Destructive commands

Never run or exercise a destructive `winter` command against a live environment you do not intend to mutate. Which
commands are destructive, and how to verify one safely, is owned by
[Verifying destructive commands safely](./context/worktree-ops.md#verifying-destructive-commands-safely).

## Further reference

| File                                                                                     | When to read                                                                                                                       |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| [context/winter-cli/index.md](./context/winter-cli/index.md)                             | You need to run a `winter` command, edit `.winter/config.toml`, or install the CLI — the hub for the whole CLI documentation tree. |
| [context/workspace-layout.md](./context/workspace-layout.md)                             | You need the workspace directory layout, feature environments, path notation, or layout rules.                                     |
| [context/worktree-ops.md](./context/worktree-ops.md)                                     | You are performing worktree git operations — creating, pulling, or destroying worktrees.                                           |
| [context/harness-runtime-ports.md](./context/harness-runtime-ports.md)                   | You need to resolve which runtime ports (fork, isolated spawn) an agent harness supports — before an execution-placement decision. |
| [workspace:/context/project/contributing.md](workspace:/context/project/contributing.md) | You are merging, pushing, or delivering work — the contributing conventions.                                                       |
| [context/github.md](./context/github.md)                                                 | You are performing a GitHub operation for this project, such as raising an issue.                                                  |
