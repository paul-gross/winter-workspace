#!/usr/bin/env bash
# Workspace-session layout hook for winter-service-tmux.
# Runs once after the wws-workspace session is created (a single pane, 0.0), with
# WINTER_TMUX_WORKTREE_DIR = the workspace root.
#
# Contract: LAYOUT ONLY. Do not use tmux send-keys, source env files, or start
# services — the orchestrator sends each workspace service's cmd after this hook
# exits. See workflow/layout-hook.sh.example for the full contract.

set -euo pipefail

: "${WINTER_TMUX_SESSION:?WINTER_TMUX_SESSION not set}"
: "${WINTER_TMUX_WORKTREE_DIR:?WINTER_TMUX_WORKTREE_DIR not set}"

# Window 0 — two side-by-side panes tailing the workspace docker service logs.
# Pane 0.0 = db-logs (the initial pane); pane 0.1 = rabbitmq-logs (split from 0.0).
# even-horizontal forces a single left-to-right row (side by side), not a grid.
tmux split-window -h -t "${WINTER_TMUX_SESSION}:0.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                     # pane 0.1 (rabbitmq-logs)
tmux select-layout -t "${WINTER_TMUX_SESSION}:0" even-horizontal

# Land on pane 0.0 (db-logs) on attach.
tmux select-pane -t "${WINTER_TMUX_SESSION}:0.0"
