---
name: ws-update
description: Integrate upstream winter framework updates from the winter remote into the workspace branch
argument-hint: "[rebase|merge]"
allowed-tools: Bash, Read, Edit, AskUserQuestion
---

# Workspace Update

Pull framework/template updates from the `winter` remote into the **workspace branch**. `/ws-setup` configures two remotes: `winter` points at the upstream framework template the workspace was cloned from, and `origin` points at the user's own fork. This skill is the guided path for taking subsequent framework updates from `winter` back into the workspace branch.

## Argument

`$ARGUMENTS` optionally pre-selects the integration approach: `rebase` or `merge`. When given, it pins Step 4 to that approach — no detection, no prompt — and the rest of the skill flows the same. Anything else (or empty) leaves the approach to be decided in Step 4.

- `/ws-update rebase` → integrate by rebase.
- `/ws-update merge` → integrate by merge.
- `/ws-update` → detect the strategy and ask if ambiguous (Step 4).

## Scope

This skill operates on the **workspace branch only**. It does **not** touch feature-environment worktrees or standalone repos — bringing upstream commits into a feature env is `ws-pull` / `winter ws merge`'s job, and pushing the updated workspace branch to `origin` is `ws-push`'s job. Run this from the workspace root, on the `workspace` branch.

## Big picture

A workspace is the framework (`winter/<branch>`) plus its own customizations, carried as a small history on top of it — see [context/workspace-layout.md](./context/workspace-layout.md) for the lineage model (the "one customization commit on top of `winter/master`" shape and the `git show winter/master:<path>` inherited-vs-owned test). There are **two strategies** for taking framework updates, and a given workspace uses one consistently:

- **Rebase strategy** — the workspace is a small stack of customization commits replayed onto `winter/<branch>` each update, kept as a clean "N commits above winter" shape. Best for a personal/solo workspace.
- **Merge strategy** — `winter/<branch>` is merged in periodically, accumulating merge commits but never rewriting the workspace's history. Best for a shared or already-published workspace branch.

Which one a workspace uses is read from its history in Step 4 — a workspace merge commit confirms the merge strategy; otherwise the choice is ambiguous and the skill asks (or honors a `rebase`/`merge` argument).

### Root-doc conflicts

Because a workspace replaces the framework's root `README.md` (and may customize `PRINCIPLES.md`) with its own, every upstream edit to those files collides on that path. That's expected and routine — there's no special git machinery to avoid it. When it happens, **always resolve in favor of the workspace's own version** (Step 5): the workspace owns its root docs, so upstream's edits to them are discarded. The only subtlety is that the "keep ours" flag flips with the strategy — `--ours` under merge, `--theirs` under rebase — covered in Step 5.

## Preconditions

Confirm the `winter` remote is configured before doing anything:

```bash
git remote -v
```

**If there is no `winter` remote**, offer to wire it up instead of stopping — this is the same remote `/ws-setup` configures (the framework upstream the workspace was cloned from). Tell the user what's missing, then ask via `AskUserQuestion` whether to add it:

- **Add `winter` → `https://github.com/paul-gross/winter.git`** (the framework source) — the default, matching what `/ws-setup` sets up.
- **Use a different upstream URL** — for a self-hosted or differently-named framework upstream; ask for the URL and use it verbatim.

On confirmation, narrate and run (substituting the chosen URL):

```bash
git remote add winter https://github.com/paul-gross/winter.git
```

Then continue. Do **not** fall back to `origin` — `origin` is the user's fork, not the framework upstream. If the user declines to add a remote, stop here (there is no upstream to update from).

**If a `winter` remote exists**, continue.

## Step 1 — Fetch the winter remote

```bash
git fetch winter
```

Report what came down (new commits on the upstream branch, or already up to date).

## Step 2 — Resolve the upstream branch

Detect the framework's default branch on the `winter` remote:

```bash
git rev-parse --abbrev-ref winter/HEAD   # e.g. "winter/master"
```

If that fails (no remote HEAD recorded), fall back to `winter/master`, and if that ref doesn't exist either, ask the user which upstream branch to integrate.

Show how far behind the workspace branch is, so the user knows what they're about to take:

```bash
git log --oneline HEAD..winter/<branch>
```

If there is nothing to integrate (the range is empty), say so — "Already up to date with `winter/<branch>` — nothing to integrate." — and stop. Otherwise there are upstream changes to take, so continue.

## Step 3 — Handle a dirty working tree

There are upstream changes to integrate, so check the working tree before touching it:

```bash
git status --porcelain
```

If it is clean, continue to Step 4. If it is dirty, **don't integrate silently over it** — show the user what's uncommitted and ask via `AskUserQuestion` how to proceed:

- **Stash, integrate, then pop** — stash the dirty changes, run the integration, then restore them on top. For a **rebase**, use the built-in `git rebase --autostash` (Step 5). For a **merge**, stash first (`git stash push -u`), merge, then `git stash pop` — and warn that the pop can itself conflict with freshly integrated changes, which the user would then resolve.
- **Abort** — stop here and let the user commit or handle the changes themselves, then re-run `/ws-update`.

Carry the choice into Step 5 (add `--autostash` to the rebase, or run the explicit stash/pop around the merge). Only stash when the user opts in.

## Step 4 — Choose merge or rebase

**If `$ARGUMENTS` pinned the approach** (`rebase` or `merge`), use it directly — skip detection and the prompt entirely. Just confirm in one line ("Integrating by rebase, as requested.") and go to Step 5. The argument is an explicit override; honor it even if it differs from the detected strategy.

Otherwise, detect the strategy from the workspace's history now (the branch was resolved in Step 2). A merge commit of the workspace's own is the one unambiguous signal — count them:

```bash
git rev-list --min-parents=2 --count HEAD ^winter/<branch>
```

- **`≥1` — merge strategy confirmed.** The workspace already preserves history with its own merge commits. Just **merge** `winter/<branch>` in — no need to ask. Tell the user why ("this workspace integrates winter by merging, so I'll keep doing that").
- **`0` — ambiguous to the log, but resolved for this workspace.** No merges unique to the workspace, which would normally be indistinguishable between a rebase-strategy workspace and a fresh install. This workspace has recorded its convention: **default to rebase** — integrate by rebase without asking. (This is the recorded preference from a prior update; the merge-confirmed `≥1` branch above still takes precedence whenever it applies.)

So the log can only ever *confirm* the merge strategy; a `0` count is "unknown," never "rebase" (which is why Step 6 exists — to record a rebase default here).

## Step 5 — Integrate

If the user opted into stashing a dirty tree (Step 3), fold it in here.

**Rebase:**

```bash
git rebase winter/<branch>              # add --autostash if stashing a dirty tree
```

**Merge:**

```bash
git stash push -u                       # only if stashing a dirty tree
git merge winter/<branch>
git stash pop                           # only if you stashed; may itself conflict
```

### Resolving a root-doc conflict

If the integration conflicts **only** on `README.md` and/or `PRINCIPLES.md`, resolve them automatically in favor of the **workspace's own version**, then explain why:

> "`README.md` / `PRINCIPLES.md` conflicted because the workspace keeps its own root docs while upstream edited theirs. This is expected on a framework update — I'm keeping the workspace's versions and discarding the upstream edits to these two files, which is the standing convention for workspace root docs."

The `--ours` / `--theirs` meaning is **inverted between merge and rebase** — pick the flag that keeps the *workspace's* content:

- **During a merge**, HEAD is the workspace branch, so the workspace version is `--ours`:
  ```bash
  git checkout --ours -- README.md PRINCIPLES.md
  git add -- README.md PRINCIPLES.md
  git merge --continue
  ```
- **During a rebase**, HEAD is the upstream being replayed onto and the workspace commit is the one being applied, so the workspace version is `--theirs`:
  ```bash
  git checkout --theirs -- README.md PRINCIPLES.md
  git add -- README.md PRINCIPLES.md
  git rebase --continue
  ```

(Only run the checkout for files that actually conflicted — use `git status` to see which of the two did.)

**If anything *other* than `README.md` / `PRINCIPLES.md` conflicts**, do **not** auto-resolve it. Resolve the root docs as above, then surface the remaining conflicts to the user and work through them together (or, for a rebase you'd rather not untangle, offer `git rebase --abort` / `git merge --abort` to back out cleanly).

## Step 6 — Offer to record a rebase default (only if you just *asked* and the user chose rebase)

This step applies **only** when Step 4 hit the **ambiguous** case (count `0`), you prompted the user, and they chose **rebase**. Skip it otherwise — when the approach was pinned by `$ARGUMENTS`, when the merge strategy was confirmed from history, or when the user chose merge.

Why this is a rebase-only offer: a merge leaves a merge commit, so next time Step 4's detection *confirms* merge on its own — it never stays ambiguous. A rebase leaves the workspace's merge count at `0`, so the log can never tell a rebase-strategy workspace apart from a fresh install, and this skill will keep asking on every update. Recording the preference is the only way rebase carries forward.

Ask via `AskUserQuestion`, explaining the ambiguity:

> "The rebase-vs-merge choice is ambiguous to an agent — a rebase leaves no signal in the history, so I had to ask. I can record rebase as this workspace's default by editing this skill, so future `/ws-update` runs rebase automatically instead of asking. Future agents would then carry the convention forward. Update the skill?"

- **Yes** → edit this skill file (`.claude/skills/ws-update/SKILL.md`): in **Step 4**, rewrite the **`0` — ambiguous** bullet so it defaults to rebase without prompting — replace its "there's **no default — ask** … whether to **rebase** or **merge** …" with something like "**default to rebase** — the recorded convention for this workspace; integrate by rebase without asking." Leave the `≥1` merge-confirmed bullet untouched. Then tell the user the skill is now modified and they should commit that change to carry the convention forward — it's a workspace customization, separate from the framework update you just integrated.
- **No** → leave the skill unchanged; you'll ask again next time.

## Step 7 — Verify the tree is clean

After the merge/rebase completes, confirm there is nothing left unresolved:

```bash
git status
```

The integration must be complete: no rebase/merge in progress and no unmerged paths. If `git status` still shows either, the integration isn't done — finish it before reporting success. (A modified `ws-update` SKILL.md from Step 6 is an expected, separate change — not an unfinished integration; mention it so the user can commit it.)

## Report

Summarize the integration in one block:

```
## Update: workspace ← winter/<branch>

- Fetched: <N new upstream commits | already current>
- Integrated by: rebase | merge
- Root-doc conflicts: README.md, PRINCIPLES.md resolved in favor of workspace (or: none)
- Other conflicts: <none | list, how resolved>
- Rebase default recorded in skill: yes (commit it) | n/a
- Tree: clean
```

Then point at the next step if relevant: "To publish the updated workspace branch to your fork, run `/ws-push`." (this skill does not push).
