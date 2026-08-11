# GitSeek V1 requirements status

This checklist maps the V1 project specification to the current repository. A feature is marked
complete only when it has an implemented user path and a repeatable verification path.

## Complete

- Anonymous natural-language repository search.
- Learning and first-contribution search modes.
- Structured query planning with model and rule-based fallback.
- GitHub live search merged with a synchronized local repository index.
- Deterministic archive, language, license, activity, and size filtering where evidence exists.
- Bounded Agent workflow with parsing, planning, retrieval, investigation, verification, one retry,
  and persisted step traces.
- Read-only repository investigation for README, community files, tests, CI, dependency files, and
  other engineering signals.
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

## Partial

- Initial repository index: resumable seed tooling targets 3,000 repositories, but production index
  size and scheduled freshness are not yet continuously verified.
- Platform and environment constraints: parsed and displayed, but not all repositories provide
  enough structured evidence for strict enforcement.
- Data freshness: search results now include `fetched_at`, seven-day `valid_until`, and a manual
  recheck path; scheduled background refresh and production freshness alerts are still missing.
- Retrieval: GitHub Search, PostgreSQL full-text search, and SQLite fallback exist; vector retrieval
  and embedding-by-commit caching are not implemented.
- Deep investigation: the Agent investigates the top 1-3 repositories rather than the planned top
  20, to keep public-demo latency and GitHub usage bounded.
- Health score: documentation and engineering signals exist, but release cadence, maintainer response
  time, contributor continuity, and PR interaction are not yet complete.
- Search progress: bounded step summaries are shown after a run; SSE incremental progress is not yet
  implemented.
- Evaluation: a versioned 40-case constraint suite, category breakdowns, and visible failures are
  available, but the planned 100-150 human relevance cases, Recall@10, nDCG@10, pairwise accuracy,
  and second-annotator review are absent.
- Observability: Agent traces and durations are persisted; token cost, cache hit rate, and version trend
  dashboards are not complete.
- Reliability: model and GitHub degradation are visible; public rate limiting, scheduled stale-Issue
  detection, and broader fault-injection coverage remain incomplete.

## Not implemented in V1 yet

- GitHub GraphQL batching and OSS Insight integration.
- Redis-backed task queue, scheduler service, and automatic daily/weekly refresh jobs.
- README/CONTRIBUTING section embeddings and pgvector recall.
- MLflow experiment tracking and the required ablation suite.
- GitHub OAuth personalization, profile export, and profile deletion.
- Learning-to-rank training and personalized reranking.
- Admin sync API with authentication.
- End-to-end Playwright suite and production-like 150-case evaluation gate.
- Demo video and final experiment report.

## Recommended implementation order

1. Add the 100-150 human relevance dataset and Recall/nDCG scorers alongside the parser suite.
2. Add scheduled index freshness and production freshness alerts.
3. Add vector recall and an ablation comparison against keyword-only retrieval.
4. Expand repository health features with Release, PR response, and contributor continuity signals.
5. Add SSE progress, public rate limiting, end-to-end tests, and production monitoring.
