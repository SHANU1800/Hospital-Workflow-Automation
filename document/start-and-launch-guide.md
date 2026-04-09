# Start and Launch Guide (Neon DB)

This project now uses **external PostgreSQL (Neon)** for database persistence.
No local Docker database container is used.

## Quick Start (recommended)

1. Open `hospital-agent-system/.env`
2. Ensure both are set:
   - `DATABASE_URL` (async URL)
   - `DATABASE_URL_SYNC` (sync URL)
3. From repo root, run:
   - `run-project.bat`

What the launcher does:

- Validates Docker and Compose availability
- Validates `.env` and `DATABASE_URL`
- Rejects old local-db values like `db:5432` or `localhost:5433`
- Builds and starts the app container
- Waits for `/health`
- Runs seed sync (`scripts/seed_neon_db.py`) inside container
- Opens:
  - Dashboard: `http://localhost:8000`
  - API docs: `http://localhost:8000/docs`

## Manual Start (optional)

From `hospital-agent-system`:

- Start app container: `docker compose up --build -d`
- Seed Neon DB: `docker compose exec -T app python scripts/seed_neon_db.py`
- Check logs: `docker compose logs --follow --tail=80`

## Verify Seed Data

From `hospital-agent-system`:

- `python scripts/verify_seed_counts.py`

You should see non-zero counts for key tables (patients, doctors, appointments, slots, claims, notifications, execution logs, etc.).

## Common Issues

### 1) Launcher says DATABASE_URL points to old local DB
Update `hospital-agent-system/.env` to Neon/external DB URLs.

### 2) Health check timeout
Run:

- `docker compose logs --tail=120`

Check networking/firewall and DB reachability.

### 3) Seed failed in launcher
Run manually:

- `docker compose exec -T app python scripts/seed_neon_db.py`

Then verify with `python scripts/verify_seed_counts.py`.
