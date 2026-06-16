# Guide: Creating contributing.md

## What it is

`workspace:/context/project/contributing.md` defines what happens after work in a feature worktree is complete — how code gets from a Greek letter branch into the project's mainline and delivered.

## Why it exists

Different projects have different delivery workflows. Some merge directly to main, others require pull requests. Some run linters before committing, others have CI that handles it. Winter doesn't prescribe any of this — the contributing file captures the specific project's policies so agents can follow them consistently.

## How it is used

- Referenced by agents when completing a feature (see the "Follow the project's contributing conventions when completing work" rule in CLAUDE.md `## Rules`)
- Referenced by the `/commit` skill for commit message conventions
- Should be specific enough that an agent can execute the full delivery flow without asking questions

## How to create it with the user

Offer the user two approaches: *"I can research your codebase to figure out your existing conventions, or you can walk me through them. Which do you prefer?"*

**If researching automatically:** Spawn an Opus subagent to explore the project repos. The subagent examines recent git log history for commit message patterns, looks for existing `CONTRIBUTING.md` files, checks for linter/formatter configs (`.eslintrc`, `.prettierrc`, `.editorconfig`), pre-commit hook configs (`.husky/`, `.pre-commit-config.yaml`), CI/CD pipeline definitions, and PR templates. Using a subagent keeps the research out of the main setup context — we only care about the findings. The subagent reports back a structured summary, and you present those findings to the user for confirmation.

**If the user prefers a guided approach**, walk through the steps below.

### 1. Commit conventions

Ask: *"What commit message format does this project use? (e.g., Conventional Commits, free-form, ticket numbers in the message)"*

Probe for:
- Required format or prefix (e.g., `feat:`, `fix:`, `JIRA-123:`)
- Scope conventions
- Whether a body is expected for non-trivial changes
- Co-authorship line preferences

### 2. Pre-commit checks

Ask: *"Are there any checks that should run before committing? (e.g., linting, formatting, type checking, tests)"*

Probe for:
- Specific commands (e.g., `npm run lint`, `prettier --write .`, `cargo fmt`)
- Whether these should run automatically or only when the user asks
- Are there pre-commit hooks already configured in the repo?

### 3. Delivery method

Ask: *"How does completed work get into the main branch? (e.g., pull request, merge request, direct merge, rebase)"*

Probe for:
- PR/MR workflow — which tool? (GitHub, GitLab, Bitbucket)
- Branch target — merge into `main`, `development`, or something else?
- Merge strategy — squash, rebase, merge commit?
- Are there required reviewers or CI checks that must pass?

### 4. Post-delivery

Ask: *"Is there anything that needs to happen after merging? (e.g., deploy, tag a release, update a changelog, notify someone)"*

### 5. Multi-repo considerations

If the workspace has multiple repos, ask: *"Do all repos follow the same delivery process, or do some differ?"*

Capture per-repo differences if they exist.

### Output

Write the result to `workspace:/context/project/contributing.md`. Structure it with clear sections that an agent can reference quickly:
- Commit message format (with examples)
- Pre-commit checks (exact commands)
- Delivery steps (exact commands or tool invocations)
- Post-delivery steps (if any)
