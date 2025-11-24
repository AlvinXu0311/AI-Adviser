# Docker Quick Start

This repo includes a `backend/Dockerfile` and a `docker-compose.yml` to run the backend together with Redis.

Quick start (from repo root):

```bash
# Build and start backend + redis (foreground)
docker compose up --build

This compose now runs a full development stack: `frontend` (React/Vite dev server), `backend` (FastAPI), `redis` and `db` (Postgres). It also includes an `init_db` one-shot job to initialize the Postgres schema using `database/scripts/init_db.py`.

Important: the `backend` service is configured to use `DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/mis520` by default — change credentials via environment or an override file for production.

# Or run in background
docker compose up --build -d

# Tail backend logs
docker compose logs -f backend

# Stop and remove
docker compose down
```

Notes:
- Backend API: http://localhost:8000
- Redis: localhost:6379 (exposed for convenience)
- The compose config mounts `./backend` into the container for fast dev iteration. If you prefer a non-mounted production image, remove the `volumes` entry from the `backend` service in `docker-compose.yml`.

Local dependency install (if you prefer not to use Docker for dev):

Backend:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
# create .env from template if needed
cp backend/.env.example backend/.env
```

Frontend:
```bash
cd frontend
npm ci
cp .env.example .env # if exists
npm run dev -- --host 0.0.0.0 --port 5173
```

Run full stack with Docker (recommended for reproducible dev):

```bash
# Build and start backend + redis + postgres + frontend
docker compose up --build

# Run DB initialization (one-shot service executes automatically when you bring up compose because of depends_on condition). Alternatively run manually:
docker compose run --rm init_db

# Or background
docker compose up --build -d

# Tail logs
docker compose logs -f backend

# Stop and remove
docker compose down
```

Verify services:

```bash
# Backend
curl http://localhost:8000/health

# Memory stats (should show redis_connected)
curl http://localhost:8000/api/chat/memory/stats

# Frontend (React dev): http://localhost:5173
```

Environment variables:
- `REDIS_HOST=redis` and `REDIS_PORT=6379` are set in the compose file.

Next steps:
- Consider adding a non-root user in `backend/Dockerfile` for production security.
- Add healthchecks to `docker-compose.yml` if you want to wait-for-redis semantics.
