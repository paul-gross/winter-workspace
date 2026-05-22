---
name: ws-setup
description: Idempotent setup and configuration of a winter workspace to connect and interact with a set of application repositories — safe to re-run any time
---

# Workspace Setup

This skill is an interactive walkthrough that sets up and configures a winter workspace to connect with a set of application repositories. Run it on a fresh clone, or any time you want to (re)configure the workspace — declare new project repos, set git identity, create the alpha environment, wire up project-setup/workflow/contributing rules.

**Idempotent:** safe to re-run at any time. Before each step, check the current state of the workspace. If the step is already done, **say so explicitly** ("your workspace remote is already configured — skipping") and move on. Don't silent skip.

## How to run this skill

This is a guided walkthrough, not a script. Your job is to teach the user how their workspace is wired together while configuring it. Be verbose, be explicit, and be patient.

**Pacing rules — strict, no exceptions:**

- **One question at a time.** Never ask the user two things at once. No compound "and / or" questions. If a step needs three pieces of info, ask three times across three turns.
- **One step at a time.** Don't preemptively run a later step's commands while the current step is still in progress. Finish the work for the current step before starting the next.
- **Don't say step numbers.** Don't say "step 1 of 9" or "step 3" or "next step" — just describe what's happening and what's next. The user shouldn't be tracking a counter.
- **Speak before acting.** At the start of every step, send a short message that describes what's about to happen and *why* it matters. Don't dive straight into a question or a command.
- **Narrate actions.** Before running a command or editing a file, tell the user what's about to happen ("Renaming `origin` to `winter`, then adding your fork as the new `origin`..."). After it runs, tell them what changed.
- **Don't pause between steps.** When a step's work is done, report what changed in one line and move directly into the next step. Don't ask "ready for the next one?" — just continue. The user can interrupt at any time.
- **Show, don't hide.** When you skip a step because the state is already correct, *show* what you found ("`.winter/config.toml` already has 2 repos declared: `foo`, `bar`. Skipping declaration."). Never silent skip.

## Prerequisites

Before running this skill:
- Read [ai/workspace-layout.md](./ai/workspace-layout.md) to understand the workspace topology and directory layout
- Read [ai/worktree-ops.md](./ai/worktree-ops.md) to understand the exact git commands for this topology

## Opening preamble (always send first)

Before doing anything, send a short orientation message, then continue straight into the first step:

> "I'll walk you through setting up your winter workspace. Stop me or ask questions at any time."

Don't wait for a "go" signal — just begin.

## Steps

### 1. Configure workspace remote

**Explain first:** "When you cloned this workspace, `origin` points at the upstream winter template. Your project-specific changes shouldn't push back to the framework — they belong in your own fork. We'll rename the existing `origin` to `winter` (so you can still pull future framework updates), then point a new `origin` at your fork."

Check the current remote setup:
```bash
git remote -v
```

**If a project-specific `origin` is already configured** (i.e. `origin` does *not* point at the upstream winter template, or a `winter` remote already exists alongside it), tell the user what you found:

> "Your remotes are already set up: `origin` → `<url>`, `winter` → `<url>`. Skipping."

Then continue to the next step.

**Otherwise**, ask **one** question first:

**"Have you already created a fork or empty repo (e.g. on GitHub/GitLab) to push this workspace to?"**

- If **no**: tell the user to go create one and paste the URL when ready. Stop and wait — don't ask anything else this turn.
- If **yes**: ask the next question on the next turn — **"What's the URL?"**

Once they provide the URL, tell them what's about to happen:

> "I'll rename the current `origin` to `winter`, add `<url>` as the new `origin`, and push the `workspace` branch with upstream tracking."

Then run:
```bash
git remote rename origin winter
git remote add origin <user-provided-url>
git push -u origin workspace
```

Report briefly: "Done — `winter` now points at the framework upstream, `origin` points at your fork, and `workspace` is pushed and tracking." Then continue to the next step.

### 2. Declare project repos

**Explain first:** "Project repos are listed in `.winter/config.toml` as `[[project_repository]]` entries. The winter CLI uses this list to know which repos to clone into `projects/` and which ones to worktree when you create a feature environment. Most workspaces start as a monorepo with a single repo, but you can declare as many as you want. We'll add them one at a time."

Read `.winter/config.toml` and check existing `[[project_repository]]` entries.

**If one or more repos are already declared**, list them by name + url, then ask **one** question:

**"You already have these repos declared: `<list>`. Want to add another, remove one, or move on?"**

- "move on": continue to the next step.
- "remove": ask **"Which one?"** Once given, delete the matching block and confirm what changed. Then ask **"Anything else, or move on?"**
- "add": fall through to the add flow below.

**If none are declared**, tell the user: "No repos declared yet — let's add the first one." Then start the add flow.

**Add flow (one repo at a time, one question per turn):**

1. Ask: **"What's the clone URL of the repo?"** (e.g., `git@github.com:user/repo.git`)

2. Once they answer, derive the repo name from the URL: take the last path segment, strip a trailing `.git`. Tell the user: "I'll call this repo `<derived-name>` (last segment of the URL, `.git` stripped)."

3. Tell them what's next: "Now I'll detect the repo's default branch by querying the remote — this matters because `winter ws init <name>` branches feature worktrees off the declared `main_branch`, and the workspace-level fallback is `main`, which silently breaks for repos that use `master` or `develop`."

   Run:
   ```bash
   git ls-remote --symref <user-provided-url> HEAD | awk '/^ref:/ { sub("refs/heads/", "", $2); print $2; exit }'
   ```

   Report the result: "Default branch is `<branch>`."

   If the command fails (auth, network, empty output), tell the user it failed and ask: **"What's the default branch of this repo?"**

4. Tell them: "Adding this entry to `.winter/config.toml`..." Then append:
   ```toml
   [[project_repository]]
   name = "<derived-name>"
   url = "<user-provided-url>"
   main_branch = "<detected-branch>"
   ```
   Always write `main_branch` explicitly, even when it's `main` — it makes the config self-describing and resilient to future upstream HEAD changes. No `cmd`, `pinned`, `alias`, or `git_excludes` here — those come later.

   Confirm: "Added `<name>` (default branch `<branch>`)."

5. Ask **one** question: **"Add another repo, or move on?"**
   - "add": loop back to step 1 of the add flow.
   - "move on": continue.

6. **Only if two or more repos are now declared**, ask once: **"The order in `.winter/config.toml` controls how repos appear in the `winter dashboard` TUI. Current order: `<list>`. Want to reorder?"**
   - If yes, take the user's preferred order and reorder the blocks in `.winter/config.toml`.
   - If no, continue.

When done, briefly confirm "Repos declared." and continue.

### 3. Resolve git identity

**Explain first:** "When `winter ws init` clones each repo (next), it can stamp a per-repo git identity onto each clone. This is useful if you want this workspace's commits to use a specific name/email different from your global git config — e.g. a work email for a work workspace. Per-repo identity only kicks in if `.winter/config.local.toml` declares a `[git]` block; otherwise repos inherit your global config. This decision happens before cloning so the right identity gets applied."

Check `.winter/config.local.toml` for a `[git]` block.

**If a `[git]` block already exists**, read its values and tell the user:

> "Your workspace currently uses identity `<name> <email>` for repo commits."

Then ask **one** question:

**"Keep this identity, change it, or drop the workspace-specific block and fall back to your global git config?"**

- "keep": continue.
- "drop": delete the `[git]` block from `.winter/config.local.toml`, confirm what changed, continue.
- "change": fall through to the prompt-for-name/email flow below.

**If no `[git]` block exists**, read the user's global identity for context:
```bash
git config --global user.name
git config --global user.email
```

Tell the user what you found: "Your global git identity is `<name> <email>`." (If either is unset, say so explicitly — only the workspace-specific option will be valid.)

Ask **one** question:

**"Use your global identity for this workspace's repos, or set a workspace-specific identity?"**

- "global": tell them "Got it — `winter ws init` will skip per-repo identity and commits will fall through to your global config." Continue.
- "workspace-specific": ask **"What name should this workspace use for commits?"** Wait for the answer. Then on the next turn ask **"And what email?"** (one question at a time). Once you have both, tell them "Writing the `[git]` block to `.winter/config.local.toml`..." and append:
  ```toml
  [git]
  user.name = "..."
  user.email = "..."
  ```
  Confirm: "Workspace identity set to `<name> <email>`."

### 4. Clone project repos

**Explain first:** "Now cloning the declared repos. This runs `winter ws init` (no arguments). The CLI reads `.winter/config.toml`, clones every declared repo into `projects/<name>/`, writes git-exclude entries, applies the git identity from the previous step, and runs each repo's `cmd` list (we haven't defined any yet — that comes later). It's idempotent: repos that already exist are left alone."

Tell the user: "Running `winter ws init`..."

Run:
```bash
winter ws init
```

Report what was cloned vs. skipped (read the CLI output and summarize), then continue.

### 5. Create project integration directory

**Explain first:** "Creating `workspace:/ai/project/` — this is where project-specific markdown lives: contributing rules, development checklists, architecture notes, anything the workspace and its agents should know about your projects. It lives here in the workspace, *not* in the project repos themselves — the project repos know nothing about winter. Agents look here first when answering project questions. This folder is intended to be committed: it's the glue layer between winter and your application source code, so anything you want future agents (or teammates) to know about your projects belongs here, versioned alongside the workspace."

Tell the user: "Creating the directory..."

```bash
mkdir -p ./ai/project
```

Confirm: "Created `workspace:/ai/project/`."

Then add a forward-looking hint:

> "If your project's agentic harness (agents, skills, project-specific docs) grows substantial, you can later extract it into its own repo and pull it back in as a winter extension — declared in `.winter/config.toml` as a `[[standalone_repository]]`. That keeps it versioned independently and reusable across workspaces, while still surfacing its agents/skills here via the auto-managed `# Winter Extensions` section in CLAUDE.md. Not something to do now — just good to know."

### 6. Set up project-setup.md (optional)

**Explain first:** "Now an optional but recommended setup: project-setup.md. **Best done before creating any feature environment.** It captures your application-specific setup: installing dependencies, generating env files, provisioning per-worktree databases, building artifacts, anything else needed to bring a fresh worktree to a runnable state. The output is two artifacts: per-repo `cmd` lists and `git_excludes` added to `.winter/config.toml`, and a new `workspace:/ai/project/project-setup.md`. Setting this up now means feature environments are runnable from the moment they're created."

Ask **one** question:

**"Want to set up project-setup.md now?"**

- "no" or "later": continue.
- "yes": follow [ai/setup-project-setup.md](./ai/setup-project-setup.md) — that guide produces the two artifacts. After it's finished, tell the user: "Now applying the new config to all existing worktrees so the `cmd` list runs everywhere..." and run:
  ```bash
  winter ws init --all
  ```
  This reruns each repo's `cmd` list and writes any new `git_excludes` into every clone (source checkouts and feature worktrees). Report what changed.

### 7. Create the alpha feature environment (optional)

**Explain first:** "Feature environments are where actual development happens. By convention the first one is named `alpha`. The Greek-letter naming isn't arbitrary — it's how each environment gets a stable, memorable, never-colliding block of 100 ports: alpha → 4100s, beta → 4200s, gamma → 4300s, and so on. Greek letters have fixed indices 1–24 reserved up front. Arbitrary names (like `feature-foo`) work too — they get a hashed index in a separate range, so they never collide with Greek letters, but they *can* collide with other arbitrary names (rare in practice, but possible if you run several ad-hoc envs at once). For predictability, prefer the next available Greek letter. `winter ws init alpha` creates the `alpha/` directory, makes a per-repo worktree on branch `alpha` (cut from each repo's `main_branch`), copies the git identity, writes git-excludes, runs each repo's `cmd` list (so any project-setup commands from the previous step apply automatically), seeds `.winter.env` with `WINTER_ENV`/`WINTER_ENV_INDEX`/`WINTER_PORT_BASE`, and runs every installed extension's `on_env_init` hook."

Ask **one** question:

**"Create the alpha feature environment now?"**

- "no": continue.
- "yes": tell them "Running `winter ws init alpha`..." then run:
  ```bash
  winter ws init alpha
  ```
  Report the result — directories created, branches cut, commands run, hooks fired.

### 8. Run feature-environment setup steps from installed extensions

**Explain first:** "Each winter extension can contribute its own setup workflow that needs to run before feature environments work properly (e.g. `winter-service-tmux` needs you to define which services to run via `./up`/`./down`). I'll go through every installed extension and check whether it has a 'Feature environment setup steps' section in its `index.md`. Extensions without one get skipped."

Look at `workspace:/CLAUDE.winter.md` — that file (imported by the `# Winter Extensions` section in `workspace:/CLAUDE.md`) lists every installed extension. If `CLAUDE.winter.md` doesn't exist, no extensions are installed and this step is a no-op. Tell the user: "Installed extensions: `<list>`."

Then, for each extension **one at a time**:

1. Tell the user: "Checking `<ext-name>`..."
2. Read that extension's `index.md` (the path shown in the block, e.g. `./winter-service-tmux/index.md`).
3. If the extension has a **"Feature environment setup steps"** section, tell the user what setup it needs and walk them through whatever it describes — typically that's another linked markdown guide. Treat each extension's walkthrough as its own mini-walkthrough: keep the same explain → ask → execute → confirm pattern, one question per turn.
4. If no such section exists, tell the user "No feature-environment setup needed for `<ext-name>`." and move to the next extension.

Examples of extensions that contribute feature-environment setup steps:
- `winter-service-tmux` — generates `workspace:/ai/project/workflow.sh` so `./up`/`./down`/`./status` know which services to run.

If no extensions are installed, or none declare feature-environment setup steps, tell the user "No extension setup needed." and continue.

### 9. Set up contributing.md (optional)

**Explain first:** "Last setup item: contributing.md. This file defines how completed work is delivered: PRs, merge strategy, linting, commit conventions. Agents read it when wrapping up work on a worktree, so without it they have to guess at your conventions. Optional, but recommended if you have any preferences about how commits or PRs should look."

Ask **one** question:

**"Set up contributing.md now?"**

- "no" or "later": continue.
- "yes": follow [ai/contributing-setup.md](./ai/contributing-setup.md) to work with the user.

### Final report

Summarize everything that happened in a single message:
- Workspace remote: configured / already set up
- Repos declared and cloned: `<list>`
- Git identity strategy: workspace-specific / global / unchanged
- Standalone extensions: `<list>` (cloned / already existed)
- Alpha feature environment: created / skipped / already existed
- Integration files: project-setup.md / workflow.sh / contributing.md (created / skipped / already existed)
- Any manual steps still pending

End with:

> "Setup complete. You can re-run `/ws-setup` any time — it's idempotent and will only apply changes that are still needed."
