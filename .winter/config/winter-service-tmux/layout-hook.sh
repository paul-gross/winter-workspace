#!/usr/bin/env bash
# Layout hook for the winter workspace tmux session.
# Ported from setup-tmux.sh setup_tmux() — pane geometry ONLY.
#
# Contract: LAYOUT ONLY. Do not use tmux send-keys, source env files, or start
# services. The orchestrator handles all of that after this hook exits.
# See workflow/layout-hook.sh.example for the full contract documentation.

set -euo pipefail

: "${WINTER_TMUX_SESSION:?WINTER_TMUX_SESSION not set}"
: "${WINTER_TMUX_WORKTREE_DIR:?WINTER_TMUX_WORKTREE_DIR not set}"

# ---------------------------------------------------------------------------
# Window 0 — winter-test-service (api / web / worker). db (Postgres) and the
# rabbitmq broker run under winter-service-docker now, so this window holds only
# the three from-source services. Panes are addressed by creation-order index
# (not visual position): the initial pane plus the splits below yield pane
# 0.0=api, 0.1=web, 0.2=worker, matching config.toml.
# ---------------------------------------------------------------------------

# Pane 0.0: api — the initial pane created by `tmux new-session`.
# Already exists; nothing to do.

# Pane 0.1: web — split window 0 horizontally.
tmux split-window -h -t "${WINTER_TMUX_SESSION}:0.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 0.1 (web)
tmux split-window -v -t "${WINTER_TMUX_SESSION}:0.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 0.2 (worker)
tmux select-layout -t "${WINTER_TMUX_SESSION}:0" tiled

# ---------------------------------------------------------------------------
# Window 1 — docs server + utility shell.
# ---------------------------------------------------------------------------
tmux new-window   -t "${WINTER_TMUX_SESSION}:1" -n docs \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 1.0 (docs)
tmux split-window -v -t "${WINTER_TMUX_SESSION}:1.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 1.1 (shell)

# ---------------------------------------------------------------------------
# Pane titles — name each pane after its service. Without this, configs that
# show pane borders (`pane-border-status top`) fall back to tmux's default
# pane title: the machine hostname.
# ---------------------------------------------------------------------------
tmux select-pane -t "${WINTER_TMUX_SESSION}:0.0" -T api
tmux select-pane -t "${WINTER_TMUX_SESSION}:0.1" -T web
tmux select-pane -t "${WINTER_TMUX_SESSION}:0.2" -T worker
tmux select-pane -t "${WINTER_TMUX_SESSION}:1.0" -T docs
tmux select-pane -t "${WINTER_TMUX_SESSION}:1.1" -T shell

# ---------------------------------------------------------------------------
# Status bar — session name only. Drops tmux's hostname/clock default so an
# attached session identifies its env (` wws-alpha `) without putting the
# machine name on screen (e.g. in demo recordings).
# ---------------------------------------------------------------------------
tmux set-option -t "${WINTER_TMUX_SESSION}" status-left " #S "
tmux set-option -t "${WINTER_TMUX_SESSION}" status-right ""

# ---------------------------------------------------------------------------
# Focus — land on pane 0.0 (api) so the user sees the main service on attach.
# ---------------------------------------------------------------------------
tmux select-window -t "${WINTER_TMUX_SESSION}:0"
tmux select-pane -t "${WINTER_TMUX_SESSION}:0.0"
