# Project setup — per-environment orchestration

Steps to run **after `winter ws init <env>`** that aren't declared in `.winter/config.toml`. Most of the stack is
config-driven — dependency installs and resource setup run via `[[provision.*]]` handlers (`winter provision <env>`),
services are declared in the winter-service-tmux and winter-service-docker manifests, and every winter-test-service
variable (ports, `DATABASE_URL`, `RABBITMQ_PORT`) is declared in the `[env.feature.vars]` / `[env.workspace.vars]` bands
of `.winter/config.toml` — so this file is short.

## Host prerequisites (one-time, per machine)

- **Docker** — winter-service-docker runs the per-env Postgres `db` and the workspace-shared RabbitMQ broker as docker
  compose services. Install Docker Engine + Compose v2 and add your user to the `docker` group (re-login or
  `newgrp docker` to pick up the membership).
- **uv** — `winter provision <env>` installs the Python deps for `winter-test-service` and `winter-plugin-api` via
  `uv sync` (their `[[provision.dependency]]` handlers). Install [uv](https://docs.astral.sh/uv/):
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **Node** — `winter provision <env>` runs `npm install` for `winter-docs` and `winter-test-service:/web`. Install
  Node.js (with `npm`).

## No per-env environment step

There is nothing to append, source, or export by hand — no env file exists. The winter-test-service variables —
`WTS_WEB_PORT` / `WTS_API_PORT` on the env's port band, `WTS_DB_PORT` / `DATABASE_URL` against the shared Postgres, and
the workspace-band `RABBITMQ_PORT` — are declared once in the env-var bands of
[`.winter/config.toml`](../../.winter/config.toml), computed at runtime, and injected by `winter service` into every
provider process (tmux panes self-source the same set via `eval "$(winter env <env>)"`). Inspect the values an env's
services will see with `winter env <env>`.

## No manual database or broker provisioning

Postgres and RabbitMQ are **workspace singletons** (containers `wws-postgres`, `wws-rabbitmq`), run by
winter-service-docker at the workspace scope. Per-env isolation is carved out *inside* them by
`winter provision <env>`'s `[[provision.resource]]` handlers — a Postgres database + role `wts_<env>` and a RabbitMQ
vhost `wts-<env>` — nothing to create by hand. The `api` service creates its schema idempotently on startup
(`CREATE TABLE IF NOT EXISTS`). Teardown note: `winter ws destroy <env>` leaves the env's database and vhost in the
shared singletons — drop them manually (`docker exec wws-postgres psql -U wts -c 'DROP DATABASE wts_<env>'`;
`docker exec wws-rabbitmq rabbitmqctl delete_vhost wts-<env>`) if you want a clean slate. The singletons themselves (and
their volumes) belong to the workspace scope — `winter service down workspace` stops them.

## Service orchestration

Two providers, bound together under `[capabilities]` in `.winter/config.toml`. The from-source services (docs, shell,
api, web, worker) are declared in the winter-service-tmux
[`config.toml`](../../.winter/config/winter-service-tmux/config.toml) +
[`layout-hook.sh`](../../.winter/config/winter-service-tmux/layout-hook.sh); the dockerized daemons (per-env Postgres
`db`, workspace RabbitMQ) in the
[winter-service-docker manifest](../../.winter/config/winter-service-docker/config.toml). Drive them together with
`winter service up <env>` (both providers fan out, docker first); see `winter-service-tmux:/index.md` for the
service-management rules and `workspace:/context/winter-cli/usage/service.md` for the `winter service` contract.
