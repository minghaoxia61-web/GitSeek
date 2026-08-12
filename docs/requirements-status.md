# GitSeek V1 requirements status

This checklist maps the V1 project specification to the current repository. A feature is marked
complete only when it has an implemented user path and a repeatable verification path.

## Complete

- Anonymous natural-language repository search.
- Fast-first search that races deterministic and model-assisted paths, runs GitHub term queries in
  parallel, ignores stale client responses, and defers deep investigation until a dossier is opened.
- Learning and first-contribution search modes.
- Structured query planning with model and rule-based fallback.
- GitHub live search merged with a synchronized local repository index.
- Deterministic archive, language, license, activity, and size filtering where evidence exists.
- Bounded Agent workflow with parsing, planning, retrieval, investigation, verification, one retry,
  and persisted step traces.
- Read-only repository investigation for README, community files, tests, CI, dependency files, and
  other engineering signals.
- Maintenance investigation for published release cadence, closed-PR resolution and merge ratios,
  and contributor activity distribution, with per-source degradation.
- Refreshed open-Issue recommendations that exclude pull requests, assigned work, and locked items.
- Evidence links, fetch times, confidence, score breakdowns, reasons, risks, and visible degradation.
- Result comparison for up to three repositories.
- Device-local and server-backed saved repositories.
- Helpful and not-relevant feedback, including a concrete failure reason.
- Editable repeat search, recent search history, explicit empty/error states, and API diagnostics.
- FastAPI, PostgreSQL migrations, Docker Compose, Vercel API deployment, Sites deployment, and a
  Tauri Windows package workflow.
- Unit tests and a versioned 40-case parser regression dataset with per-category quality results.
- Seven-day result validity metadata, visible freshness states, and a user-triggered repository
  recheck for investigation and Issue data.
- Authenticated daily Vercel index refresh with rotating popularity bands, stale/expired counts, and
  a visible production index diagnostic.
- Fifteen-minute database-backed search-result caching with explicit hit metadata and graceful
  fallback when persistence is unavailable.

## Partial

- Initial repository index: resumable seed tooling targets 3,000 repositories and the daily job now
  grows an underfilled index across rotating popularity bands and result pages; production growth
  still depends on a configured `CRON_SECRET`.
- Platform and environment constraints: parsed and displayed, but not all repositories provide
  enough structured evidence for strict enforcement.
- Data freshness: search results include `fetched_at`, seven-day `valid_until`, manual recheck, daily
  background refresh, and index diagnostics; external alert delivery is still missing.
- Retrieval: GitHub Search, PostgreSQL full-text search, SQLite fallback, and local multilingual
  vector recall/reranking exist. The vector encoder is process-cached; durable embedding-by-commit
  storage and an external embedding model comparison are not yet implemented.
- Deep investigation: the Agent investigates the top 1-3 repositories rather than the planned top
  20, to keep public-demo latency and GitHub usage bounded.
- Health score: documentation, engineering, release cadence, PR interaction, and contributor
  distribution signals exist; first maintainer response time still requires timeline-event sampling.
- Search progress: bounded step summaries are shown after a run; SSE incremental progress is not yet
  implemented.
- Evaluation: a versioned 40-case constraint suite and 100-case curated relevance suite now report
  Recall@10, nDCG@10, MRR@10, and keyword-versus-vector lift. Pairwise preference accuracy and a
  second-annotator review are still absent.
- Observability: Agent traces and durations are persisted; token cost, cache hit rate, and version trend
  dashboards are not complete.
- Reliability: model and GitHub degradation are visible; public rate limiting, scheduled stale-Issue
  detection, and broader fault-injection coverage remain incomplete.

## Not implemented in V1 yet

- GitHub GraphQL batching and OSS Insight integration.
- Redis-backed task queue and a dedicated long-running scheduler service.
- README/CONTRIBUTING section embeddings and pgvector recall.
- MLflow experiment tracking and the required ablation suite.
- GitHub OAuth personalization, profile export, and profile deletion.
- Learning-to-rank training and personalized reranking.
- Admin sync API with authentication.
- End-to-end Playwright suite and production-like 150-case evaluation gate.
- Demo video and final experiment report.

## Recommended implementation order

1. Add second-annotator review and pairwise preference accuracy to the relevance suite.
2. Add durable embedding-by-commit storage and compare an external embedding model.
3. Add first-response timing from Issue/PR timeline events.
4. Add SSE progress, public rate limiting, end-to-end tests, and production monitoring.
