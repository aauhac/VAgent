# Postgres validation

- Docker Compose Postgres (`docker-compose.dev.yml`): **NOT RUNNING**
- Docker daemon: `npipe:////./pipe/dockerDesktopLinuxEngine` missing
- Alembic revision added: `20260817_0005` (payment_intents, auth_sessions, order binding columns)
- SQLite in-memory/file tests for grant/replay/intent/refund: **PASS**
- Fresh `Base.metadata.create_all` in payment tests: **PASS**
- Live `alembic upgrade head` on empty Postgres: **NOT_RUN**
- Existing DB upgrade: **NOT_RUN**
- Restart persistence on live Postgres: **NOT_RUN**

RELEASE GATE: **BLOCKED_POSTGRES_NOT_VERIFIED**
