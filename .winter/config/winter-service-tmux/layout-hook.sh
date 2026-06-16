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
# Window 0 — docs server + utility shell
# ---------------------------------------------------------------------------

# Pane 0.0: docs — the initial pane created by `tmux new-session`.
# Already exists; nothing to do.

# Pane 0.1: utility shell — split window 0 vertically (top = docs, bottom = shell).
tmux split-window -v \
  -t "${WINTER_TMUX_SESSION}:0.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"

# ---------------------------------------------------------------------------
# Window 1 — winter-test-service (api / web / worker). db (Postgres) and the
# rabbitmq broker run under winter-service-docker now, so this window holds only
# the three from-source services. Panes are addressed by creation-order index
# (not visual position): the splits below yield pane 1.0=api, 1.1=web,
# 1.2=worker, matching config.toml.
# ---------------------------------------------------------------------------
tmux new-window   -t "${WINTER_TMUX_SESSION}:1" -n test-service \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 1.0 (api)
tmux split-window -h -t "${WINTER_TMUX_SESSION}:1.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 1.1 (web)
tmux split-window -v -t "${WINTER_TMUX_SESSION}:1.0" \
  -c "${WINTER_TMUX_WORKTREE_DIR}"                                    # pane 1.2 (worker)
tmux select-layout -t "${WINTER_TMUX_SESSION}:1" tiled

# ---------------------------------------------------------------------------
# Focus — land on pane 0.0 (docs) so the user sees the main service on attach.
# ---------------------------------------------------------------------------
tmux select-window -t "${WINTER_TMUX_SESSION}:0"
tmux select-pane -t "${WINTER_TMUX_SESSION}:0.0"
