#!/usr/bin/env bash
# Project tmux configuration for winter workspace scripts.
#
# Uses the setup_tmux / WINTER_TMUX_SERVICE_NAMES contract — see
# winter-service-tmux:/workflow/setup-tmux.sh.example for the canonical template.
# Machine-specific overrides go in a gitignored sibling setup-tmux.local.sh.

SESSION_PREFIX="wws"

ENV_FILE=".winter.env"

# Window 0 holds the one long-running service this workspace runs — the
# winter-docs site (Astro/Starlight) — alongside a utility shell:
#   0.0:docs   the docs dev server, bound to this env's $WINTER_PORT_BASE
#   0.1:shell  ad-hoc shell
WINTER_TMUX_SERVICE_NAMES=("0.0:docs" "0.1:shell")

# Pane 0.0: winter-docs dev server. Runs from the env's winter-docs worktree
# (the relative `cd` resolves against the worktree root the launch helper resets
# to) and binds to $WINTER_PORT_BASE so each env serves on its own port (falls
# back to Astro's default with `./up local`, which skips the env file). Served
# under the site's /winter-docs base path.
# Pane 0.1: utility shell — empty command leaves an interactive prompt.
winter_service_cmd docs  'cd winter-docs && npm run dev -- --port "${WINTER_PORT_BASE:-4321}" --host'
winter_service_cmd shell ""

setup_tmux() {
  local session="$1" dir="$2" name="$3"

  winter_tmux_send_service "$session" "0.0" "docs"

  # Split window 0 vertically (top/bottom)
  tmux split-window -v -t "$session:0.0" -c "$dir"

  winter_tmux_send_service "$session" "0.1" "shell"

  # Land focus on the docs pane
  tmux select-pane -t "$session:0.0"
}

# status_header — print the docs URL for this env above the per-pane status.
status_header() {
  local name="$1" dir="$2"
  local env_path="$dir/$ENV_FILE"
  if [[ -f "$env_path" ]]; then
    local base
    base=$(grep -oP 'WINTER_PORT_BASE=\K\d+' "$env_path" 2>/dev/null || echo "")
    [[ -n "$base" ]] && echo "  docs: http://localhost:$base/winter-docs/"
  fi
}
