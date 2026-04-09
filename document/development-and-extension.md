# Development and Extension Guide

## Running with Docker (recommended)

Project folder: `hospital-agent-system`

Expected files already present:

- `docker-compose.yml`
- `Dockerfile`
- `.env`

Start stack:

- Postgres service (`db`)
- FastAPI service (`app`)

When app starts:

- DB tables are created
- Seed data is added (first run only)
- Dashboard available at `http://localhost:8000`

## Environment variables

From `.env`:

- `DATABASE_URL` (async SQLAlchemy URL)
- `DATABASE_URL_SYNC` (sync URL)
- `APP_ENV`
- `LOG_LEVEL`

Default compose network DB host is `db`.

## Local Python run (without Docker)

You can run directly if PostgreSQL is available and `DATABASE_URL` points to a reachable instance.

Minimal dependency set is defined in `requirements.txt`.

## How to extend the system

## 1) Add a new workflow event

Edit `planner/planner.py` and add a new entry in `PLANNING_RULES`:

- choose `event_pattern`
- define ordered `task_templates`
- map params via `params_map`
- set priority

No new endpoint required if using `POST /trigger_event`.

## 2) Add a new MCP tool

In `mcp/tools.py`:

1. Create async function
2. Decorate with `@register_tool(...)`
3. Define metadata and parameters

Agents can then call it via `call_tool()`.

## 3) Add a new agent

In `agents/`:

1. Subclass `BaseAgent`
2. Implement `name`, `capabilities`, `handle_task`
3. Optionally override `receive_message`
4. Register the agent in app startup (`api/main.py` lifespan)

## 4) Add a new DB entity

In `models/database.py`:

1. Define ORM model on `Base`
2. App startup table creation includes it automatically
3. Add MCP tool(s) for controlled access

## Extension design principles

- Keep workflow logic in planner rules, not API handlers
- Keep resource access inside MCP tools, not agents
- Prefer passing reusable context between steps
- Use A2A for cross-agent dependencies
- Preserve structured logging for traceability

## Seed data reference

Current startup seed includes:

- 8 sample patients (`ID 101–108`)
- 10 sample doctors across departments

Useful for demos and dashboard quick actions.
