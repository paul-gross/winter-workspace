# Service panes

Tmux session: `<SESSION_PREFIX>-<worktree>` (e.g. `wws-alpha`).

Capture a service's output:

    tmux capture-pane -t <session>:<window>.<pane> -p | tail -20

Restart one service in place (reap its pane, re-run its command):

    ./restart <service>

Declared services:

- `docs` → `0.0`
- `shell` → `0.1`
