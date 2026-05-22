---
name: ws-work
description: Start working on a plan — use when the user says "work on <name>", "implement <name>", or "start the <name>". Reads the plan, selects a worktree, and begins implementation solo or with a team.
model: opus
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, TeamCreate, TaskCreate, TaskUpdate, TaskList, SendMessage, AskUserQuestion
---

Begin work on a plan.

## Argument Parsing

Parse `$ARGUMENTS` for:
- **Plan name** (required): kebab-case
- **Worktree** (optional): specified as `in <worktree-name>` (e.g., `in alpha`, `in beta`)

Examples:
- `/ws-work user-notifications` — plan name only, worktree will be determined
- `/ws-work user-notifications in alpha` — use the alpha worktree
- `/ws-work refactor-auth-service` — short plan, will be handled solo

## Determine the project's main branch

Follow the **Branch resolution** pattern defined in the root CLAUDE.md. Use the result as the base branch for all comparisons and worktree operations.

## Step 1: Read the work item

When the `winter-product` extension is installed, work items live under `winter-product:/`:

1. **Promoted work item** → read `winter-product:/work/<name>/00-overview.md` (and any `.tech.md` siblings under that directory).
2. **Open backlog item** (still being refined) → check `winter-product:/backlog/**/<name>.{idea,todo,work}.md`. If found, tell the user the item is in `backlog/` and ask whether to promote it via `/wp-refine <name>` first, or proceed with the open description.
3. **Workspace-relative plan files** (legacy) → fall back to a glob over the workspace for a file whose name or content matches `<name>`. Ask the user to confirm the match before proceeding.

Summarize for the user (1–2 sentences from the overview).

The earlier `winter-product:/plans/` and `winter-product:/todos/` layout has been replaced by the single `backlog/` + `work/` model.

## Step 2: Determine scope

Decide whether this is a **small/quick change** (a single self-contained change describable in 1–3 sentences, no architectural decisions, fits in one session) or a **larger multi-phase change** (separable work, possibly with a `.tech.md` and dependencies).

State your decision and reasoning to the user. Carry it forward — it informs phase assessment (Step 4) and team strategy (Step 5).

## Step 3: Determine the worktree

**If a worktree was specified in the arguments** (e.g., `in alpha`), use it. Verify it exists with `git worktree list`. If it does not exist, tell the user and ask what to do.

**If no worktree was specified**, apply this logic:

1. Check the `alpha` worktree's status:
   ```bash
   git -C ./alpha status --short
   git log --oneline <main-branch>..alpha
   ```
2. **If alpha has no uncommitted changes AND no commits ahead of the main branch**, default to alpha. Tell the user you are using alpha and proceed.
3. **Otherwise**, ask the user which worktree to use. List the available worktrees and their status (clean/dirty, commits ahead) so they can choose.

**Never create a new worktree unless the user explicitly tells you to.** If the user asks you to create one, follow the "Creating a New Worktree" workflow defined in the root CLAUDE.md.

### Baseline check (optional)

Once the worktree is selected, ask the user: **"Run a baseline check to make sure `<worktree>` is up to date and set up before we start?"**

If yes:
1. Sync the worktree against main: `winter ws sync <worktree>`
2. Reconcile setup (re-runs each repo's `cmd` list, refreshes git-excludes): `winter ws init <worktree>`
3. Report the result. If anything failed, surface it to the user and pause before proceeding.

If no, proceed straight to implementation.

## Step 4: Assess phase status

For a small/quick plan, there are no phases to assess — proceed.

For a larger plan, determine which phases are already complete and which need work:

1. Check the worktree's branch log against the main branch: `git log --oneline <main-branch>..<branch>`
2. Cross-reference commits with plan phases to determine completion status.
3. If completion status cannot be determined from commits or plan files, ask the user which phases are already done.

Summarize the plan status:
- Total phases and which are complete vs remaining
- Any prerequisites or dependencies noted in the plan

## Step 5: Determine team strategy

**Prefer solo for small/quick plans** — there's a single change, no parallelization opportunity.

For larger plans, evaluate whether the remaining work benefits from a team.

**Use a team when:**
- Multiple phases remain and phases are independent enough for parallel work
- A single phase has clearly separable work streams (e.g., backend and frontend)
- The work spans multiple service boundaries
- Verification is non-trivial (UI flows, API contracts, integration paths) — pair the developer with the appropriate verification agents

**Work solo when:**
- Only one phase remains
- The remaining work is tightly sequential
- The phases have strict dependencies that prevent parallel work

**Always tell the user your decision and reasoning before proceeding.** For example:
- Solo: "Working solo because there's one phase remaining and the work is sequential."
- Team: "Spinning up a team because phases 2 and 3 are independent — one agent can handle the API layer while another builds the UI."

If a team is warranted, present the proposed team structure to the user:
- How many agents and their roles
- Which phases or tasks each agent would handle
- Why each agent is needed
- Confirm before creating the team

## Step 6: Begin work

### Solo mode

Implement the change (or the next incomplete phase, for larger plans):
1. Read the phase document's implementation steps and any corresponding `.tech.md` file
2. Implement, committing completed work per the worktree's commit conventions

### Team mode

1. Create the team with `TeamCreate`, giving it a descriptive name based on the plan
2. Create tasks from the plan phases using `TaskCreate`, one task per phase or per separable work unit
3. Spawn teammates via the `Agent` tool, passing `team_name` to connect them to the team and setting `subagent_type` to the appropriate role
4. Each teammate's prompt should include the worktree path, the plan name, and their assigned task
5. Monitor progress via `TaskList` and coordinate integration points with `SendMessage`

In either mode, the plan documents are the source of truth for what to build.

$ARGUMENTS
