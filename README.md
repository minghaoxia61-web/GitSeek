# GitSeek

GitSeek is an evidence-backed GitHub project discovery and contribution assistant. It turns a
natural-language goal into explicit constraints, retrieves candidate repositories, applies
deterministic filters and ranking, and explains every recommendation with source evidence.

## Current milestone

The repository currently contains the first end-to-end product slice:

1. Run a FastAPI service locally or with Docker Compose.
2. Verify service health through `GET /health`.
3. Persist GitHub repository metadata through versioned database migrations.
4. Synchronize deterministic repository search results through the GitHub API.
5. Explore results through a complete repository-intelligence web interface.

The current V1 also includes a bounded Agent workflow, contribution-Issue screening, device-local
saves, feedback capture, and a deterministic smoke evaluation that reports real parser results
instead of placeholder metrics. Agent runs, step traces, search sessions, recommendation evidence,
repository snapshots, refreshed Issues, feedback, and saved repositories have database-backed
persistence. The public Sites build uses D1 for the same product activity, while the FastAPI stack
uses PostgreSQL.

The implementation is a working product slice, not the entire planning document. See
[`docs/requirements-status.md`](docs/requirements-status.md) for the current complete, partial, and
pending V1 requirements.

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
service on port `8000`. The UI reports connection, rate-limit, server, and empty-result states
explicitly; the application settings page can override the API address on the current device.

## Windows desktop application

The Tauri 2 desktop shell lives in `apps/desktop`. It reuses the React interface while keeping
GitHub and model credentials on the remote FastAPI service. Never package `OPENAI_API_KEY` or
`GITHUB_TOKEN` into the desktop client.

For local desktop development, start the API on port `8000`, then run:

```powershell
cd apps/desktop
pnpm install
pnpm run dev
```

Before building an installer, copy the desktop environment example and point it at the public API:

```powershell
Copy-Item ..\web\.env.desktop.example ..\web\.env.desktop
# Edit VITE_API_BASE_URL in ..\web\.env.desktop, for example https://api.example.com
pnpm run build
```

The build produces NSIS (`.exe`) and MSI installers under
`apps/desktop/src-tauri/target/release/bundle`. Windows builds require Rust with the stable MSVC
toolchain, Visual Studio Build Tools with the C++ workload and Windows SDK, and WebView2. The API
deployment must set `OPENSCOUT_CORS_ORIGINS` to include the browser origins plus
`tauri://localhost,http://tauri.localhost`.

If the local Windows toolchain is unavailable, run the `Build Windows desktop app` workflow from
the repository's GitHub Actions page. Enter the public API base URL when prompted, then download the
`GitSeek-Windows` artifact after the workflow finishes.

## Vercel API deployment

The repository root contains `app.py`, which exposes the FastAPI application as a Vercel Python
Function. Import the repository into Vercel with the repository root as the project root. The API
still requires an external PostgreSQL database; a Neon integration can provide `DATABASE_URL`, which
GitSeek automatically normalizes to the installed psycopg driver.

Configure these Vercel environment variables for Production, Preview, and Development as needed:

```text
DATABASE_URL=<pooled PostgreSQL connection URL from Neon>
OPENSCOUT_ENV=production
OPENSCOUT_CORS_ORIGINS=tauri://localhost,http://tauri.localhost,http://127.0.0.1:5173,http://localhost:5173
GITHUB_TOKEN=<GitHub token>
OPENAI_API_KEY=<DeepSeek API key>
OPENSCOUT_OPENAI_MODEL=deepseek-v4-flash
OPENSCOUT_OPENAI_API_URL=https://api.deepseek.com
```

Run migrations once against the cloud database before using persistence-backed endpoints:

```powershell
$env:DATABASE_URL = "<Neon connection URL>"
.\.venv\Scripts\python -m alembic upgrade head
Remove-Item Env:DATABASE_URL
```

After Vercel reports a ready deployment, verify `https://<deployment-domain>/health`, then use the
deployment origin (without `/health`) as `api_base_url` in the Windows desktop build workflow.

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

Search now merges the synchronized repository index with GitHub's live repository search. PostgreSQL
uses a generated full-text document with a GIN index; SQLite keeps a portable substring fallback for
tests. Every recommendation reports whether it came from the local index, GitHub live search, or
both, and includes the data fetch time. If GitHub is rate-limited, indexed matches remain available.

The web client uses a fast-first search path: deterministic search and model-assisted interpretation
start together, the first successful result is rendered immediately, and a later model result refines
the page without blocking it. GitHub term queries are issued concurrently with bounded 50-item pages;
repository investigation runs only after the user opens a project dossier.

Index readiness and freshness are available through `GET /api/v1/index/status`.

## Bounded Agent workflow

The web discovery flow calls `POST /api/v1/agent/runs`. A run parses constraints, records a search
plan, performs hybrid retrieval, investigates at most three top repositories, and verifies its own
recommendation evidence. Every node records status, duration, attempts, and a short summary. Failed
repository investigations are retried once unless GitHub has already reported a rate limit.

```powershell
$body = @{
  query = "找一个适合新手参与的 Python CLI 项目，MIT 许可证"
  limit = 10
  investigate_limit = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/agent/runs" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

The workflow is intentionally deterministic and read-only. It does not execute repository content,
or make GitHub changes. When `OPENAI_API_KEY` is configured, `gpt-5.6-luna` uses the Responses API
with strict structured output to infer the language, technology concepts, GitHub search terms, and
optional constraints from the complete natural-language request. The model can be changed with
`OPENSCOUT_OPENAI_MODEL` locally or `OPENAI_MODEL` in the Sites runtime. Hard filtering, ranking,
repository access, and evidence verification remain controlled by application code.

If the model is unconfigured, times out, or returns invalid output, the run falls back to the built-in
parser and reports that downgrade in `interpretation.source` and the frontend execution panel. The
ordinary `POST /api/v1/search` endpoint remains available as a lower-latency fallback.

## Repository investigation

GitSeek can now build an on-demand evidence dossier for a public repository:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/repos/fastapi/fastapi/investigate"
```

The investigator reads GitHub's community profile, repository root, workflow directory, and README.
It reports documentation, engineering, and learning-friendliness scores together with the source URL
and fetch time for every claim. Repository content is treated as untrusted data and is never executed.

## Contribution issues and feedback

GitSeek refreshes a repository's open issues before recommending a task. Pull requests, assigned
work, and locked discussions are excluded; labels, description completeness, discussion size, and
risk labels produce a bounded difficulty estimate.

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/repos/fastapi/fastapi/issues?limit=5"
```

User feedback is accepted through `POST /api/v1/feedback`. The web app preserves saved repositories
on the current device even when the feedback API is temporarily unavailable.

## Evaluation

`GET /api/v1/evals/summary` and `POST /api/v1/evals/run` execute the versioned deterministic smoke
set and return its actual constraint-parsing accuracy, complete-case pass rate, and failure samples.
This is deliberately a small engineering gate, not a substitute for the planned 100-150 case human
relevance dataset.

## Database migration

With PostgreSQL running, apply the schema:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

The first migration creates `repositories` and `repository_features`. Feature booleans are nullable
on purpose: `null` means that GitSeek has not collected enough evidence to decide.

## Synchronize seed repositories

Add a GitHub token to `.env`, apply the migration, then run:

```powershell
.\.venv\Scripts\python -m workers.sync.repositories `
  --query "language:Python archived:false pushed:>2026-02-01" `
  --pages 1
```

Each page contains at most 100 repositories. Re-running the command updates existing rows instead
of creating duplicates.

To build the initial Python index across multiple popularity bands after configuring a GitHub token:

```powershell
.\.venv\Scripts\python -m workers.sync.seed --target 3000 --pages-per-query 5
```

The seed job is resumable: repository rows are upserted, while each refresh appends an immutable
metrics snapshot. A GitHub token is strongly recommended because unauthenticated search limits are
too low for the initial 3,000-repository import.

### Scheduled refresh on Vercel

The production deployment registers a daily refresh at 03:00 UTC. Add a random value of at least
16 characters as `CRON_SECRET` in the Vercel project. Vercel sends it as a Bearer credential; the
refresh endpoint rejects missing or incorrect credentials. While the index contains fewer than
3,000 repositories, each run rotates through four popularity bands and advances across result pages
to grow the index without a manual seed process. Once the target is reached, it switches to two
popularity bands per run for bounded maintenance refreshes.

`GET /api/v1/index/status` reports fresh, stale (over 7 days), and expired (over 30 days) record
counts. The web settings screen shows the same state without exposing the refresh credential.

Equivalent searches are reused from PostgreSQL for 15 minutes. Cache hits skip GitHub entirely and
are identified by `retrieval.cache_hit` and `retrieval.cached_at` in the API response.

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
apps/desktop/      Tauri 2 Windows desktop shell and installer configuration
apps/web/          React repository-intelligence interface
packages/domain/   Shared domain contracts and configuration
packages/database/ Database engine and session factory
packages/github_client/ Typed GitHub API client
workers/sync/      Repository synchronization workers
migrations/        Alembic database migrations
tests/             Automated tests
docs/              Architecture and decision records
```
