# Project setup — per-environment orchestration

Steps to run **after `winter ws init <env>`** that aren't declared in `.winter/config.toml`. Most of the stack is config-driven — dependency installs and resource setup run via `[[provision.*]]` handlers (`winter provision <env>`), and services are declared in the winter-service-tmux and winter-service-docker manifests — so this file is short.

## Host prerequisites (one-time, per machine)

- **Docker** — winter-service-docker runs the per-env Postgres `db` and the workspace-shared RabbitMQ broker as docker compose services. Install Docker Engine + Compose v2 and add your user to the `docker` group (re-login or `newgrp docker` to pick up the membership).
- **uv** — `winter provision <env>` installs the Python deps for `winter-test-service` and `winter-plugin-api` via `uv sync` (their `[[provision.dependency]]` handlers). Install [uv](https://docs.astral.sh/uv/): `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **Node** — `winter provision <env>` runs `npm install` for `winter-docs` and `winter-test-service/web`. Install Node.js (with `npm`).

## Per-env step: append winter-test-service vars to `.winter.env`

`winter ws init <env>` seeds the managed block with `WINTER_PORT_BASE`. winter-test-service also wants its derived ports (and `DATABASE_URL`, `RABBITMQ_PORT`) in `.winter.env` so they reach every service pane and the docker db/broker compose (the orchestrator sources `.winter.env` too). Append below the managed marker — the winter-test-service ports come off `WINTER_PORT_BASE` (+10 / +11 / +12), the shared-broker port off the workspace base. **Prefix each line with `export`**: a service pane sources `.winter.env` with a plain `source`, so an unexported assignment is only a shell variable the child process (uvicorn, vite, the worker) never sees — `export` is what makes the value reach the running service.

```sh
# from the workspace root, for <env>:
base=$(grep -oP 'WINTER_PORT_BASE=\K[0-9]+' <env>/.winter.env)
wbase=$(grep -oP 'WINTER_WORKSPACE_PORT_BASE=\K[0-9]+' <env>/.winter.env)
cat >> <env>/.winter.env <<EOF

# winter-test-service — ports derived from WINTER_PORT_BASE (web +10, api +11, db +12).
export WTS_WEB_PORT=$((base + 10))
export WTS_API_PORT=$((base + 11))
export WTS_DB_PORT=$((base + 12))
export DATABASE_URL=postgresql://wts:wts@localhost:$((base + 12))/wts
# Shared RabbitMQ broker — workspace singleton on the workspace band (WINTER_WORKSPACE_PORT_BASE+1).
# The worker connects here into its per-env vhost (wts-<env>); RABBITMQ_HOST defaults to localhost.
export RABBITMQ_PORT=$((wbase + 1))
EOF
```

This step is required: the service commands (`config.toml`) read these values straight from the environment, so without the exported vars the api/web/worker bind wrong ports, fail to reach the database, or (the worker) can't find the shared RabbitMQ broker. `RABBITMQ_PORT` derives from `WINTER_WORKSPACE_PORT_BASE` (the index-0 band, not the env's own `WINTER_PORT_BASE`), because the broker is a single workspace-shared instance — every env's worker connects to the same host port.

## No manual database provisioning

Each env gets its **own** Postgres, managed by winter-service-docker: a per-env container `wts-<env>-db` on host port `WTS_DB_PORT` (`WINTER_PORT_BASE`+12), with data in the named volume `wts-<env>_postgres-data`. The `api` service creates its schema idempotently on startup (`CREATE TABLE IF NOT EXISTS`), so there is nothing to provision by hand. The per-env RabbitMQ vhost is likewise created for you by `winter provision <env>` (a `[[provision.resource]]` handler), not by hand. Teardown note: `winter service down <env>` stops the container but keeps the volume (compose down without `-v`), and `winter ws destroy <env>` also leaves it — drop it with `docker volume rm wts-<env>_postgres-data` if you want a clean slate.

## Service orchestration

Two providers, bound together under `[capabilities]` in `.winter/config.toml`. The from-source services (docs, shell, api, web, worker) are declared in the winter-service-tmux [`config.toml`](../../.winter/config/winter-service-tmux/config.toml) + [`layout-hook.sh`](../../.winter/config/winter-service-tmux/layout-hook.sh); the dockerized daemons (per-env Postgres `db`, workspace RabbitMQ) in the [winter-service-docker manifest](../../.winter/config/winter-service-docker/config.toml). Drive them together with `winter service up <env>` (both providers fan out, docker first); see `winter-service-tmux:/index.md` for the service-management rules and `workspace:/context/winter-cli/usage/service.md` for the `winter service` contract.
