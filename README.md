# OpenScout

OpenScout is an evidence-backed GitHub project discovery and contribution assistant. It turns a
natural-language goal into explicit constraints, retrieves candidate repositories, applies
deterministic filters and ranking, and explains every recommendation with source evidence.

## Current milestone

The repository currently contains the first end-to-end product slice:

1. Run a FastAPI service locally or with Docker Compose.
2. Verify service health through `GET /health`.
3. Persist GitHub repository metadata through versioned database migrations.
4. Synchronize deterministic repository search results through the GitHub API.
5. Explore results through a complete repository-intelligence web interface.

Deterministic ranking and evaluation will be added incrementally after this foundation is stable.

## Local development

Requires Python 3.12 or newer.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn apps.api.main:app --reload
```

Open <http://localhost:8000/docs> or request <http://localhost:8000/health>.

## Web application

The React interface lives in `apps/web` and includes discovery, results, repository detail,
comparison, and evaluation surfaces.

```powershell
cd apps/web
pnpm install
pnpm run dev
```

Open <http://127.0.0.1:5173>. During development, `/api` requests are proxied to the FastAPI
service on port `8000`. If the API is unavailable, the UI explicitly switches to demonstration
data so the complete product flow remains reviewable.

The first recommendation baseline is available through `POST /api/v1/search`:

```powershell
$body = @{
  query = "找一个适合 Python 初学者学习 FastAPI 的项目，MIT 许可证，最近半年有更新"
  limit = 10
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/search" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

This baseline deliberately ranks only repository metadata. Every result warns that README, tests,
and contribution guidance have not yet been verified; those claims will be added only after the
deep-investigation milestone.

## Database migration

With PostgreSQL running, apply the schema:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

The first migration creates `repositories` and `repository_features`. Feature booleans are nullable
on purpose: `null` means that OpenScout has not collected enough evidence to decide.

## Synchronize seed repositories

Add a GitHub token to `.env`, apply the migration, then run:

```powershell
.\.venv\Scripts\python -m workers.sync.repositories `
  --query "language:Python archived:false pushed:>2026-02-01" `
  --pages 1
```

Each page contains at most 100 repositories. Re-running the command updates existing rows instead
of creating duplicates.

## Tests and lint

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The Compose stack starts PostgreSQL and the API. The API is available on port `8000`.

## Project structure

```text
apps/api/          FastAPI application
apps/web/          React repository-intelligence interface
packages/domain/   Shared domain contracts and configuration
packages/database/ Database engine and session factory
packages/github_client/ Typed GitHub API client
workers/sync/      Repository synchronization workers
migrations/        Alembic database migrations
tests/             Automated tests
docs/              Architecture and decision records
```
