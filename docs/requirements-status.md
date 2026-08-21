# GitSeek V1 requirements status

This checklist maps the V1 project specification to the current repository. A feature is marked
complete only when it has an implemented user path and a repeatable verification path.

## Complete

- Anonymous natural-language repository search.
- Fast-first search that races deterministic and model-assisted paths, expands common bilingual
  intents locally, runs GitHub term queries in parallel, ignores stale client responses, and defers
  deep investigation until a dossier is opened.
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
- Optional OpenAI-compatible external embeddings, durable model-and-content-hash vector caching,
  explicit local fallback, and a repeatable external-versus-local retrieval evaluation endpoint.
- Reciprocal-rank fusion across local full-text, local semantic, and independent GitHub live-query
  channels, with per-channel candidate counts and latency diagnostics.
- Public GitHub developer profiles and evidence-limited user-to-Issue matching with skill matches,
  missing-evidence labels, fit scores, and an actionable start checklist.
- A versioned 20-pair preference set, pairwise accuracy, deterministic bootstrap lower bound, and
  feature ablations that directly changed the production popularity weight.
- Persisted per-query synchronization cursors, failed-shard recovery, and duplicate snapshot
  suppression for the production repository index.
- Streaming Agent progress with client cancellation, recent query-plan caching, configurable public
  request limits, request IDs, timing/health metrics, and desktop/mobile Playwright smoke tests.
- Twelve-hour repository dossier caching, 30-minute Issue caching, explicit cache bypass, and stale
  fallback during GitHub rate limits.
- Device-level feedback reranking with bounded positive and negative adjustments and no login.
- Tiered index refresh frequency, safe archived/inactive long-tail pruning, and an automated GitHub
  Actions quality gate for backend, retrieval, desktop, and mobile checks.
- A Windows remote-interface bootstrap that loads normal web updates without reinstalling and falls
  back to the packaged interface when the hosted app is unavailable.

## Partial

- Initial repository index: resumable seed tooling targets 3,000 repositories and the daily job now
  grows an underfilled index across Python, TypeScript, JavaScript, Java, Go, and Rust shards,
  rotating popularity bands and result pages; production growth still depends on the scheduled job.
- Platform and environment constraints: parsed and displayed, but not all repositories provide
  enough structured evidence for strict enforcement.
- Data freshness: search results include `fetched_at`, seven-day `valid_until`, manual recheck, daily
  background refresh, and index diagnostics; external alert delivery is still missing.
- Retrieval: GitHub Search, PostgreSQL full-text search, SQLite fallback, local multilingual vectors,
  and optional durable external embeddings exist. The free local path is the production default;
  external-provider comparison remains optional for deployments that already have a provider.
- Deep investigation: the Agent investigates the top 1-3 repositories rather than the planned top
  20, to keep public-demo latency and GitHub usage bounded.
- Health score: documentation, engineering, release cadence, PR interaction, and contributor
  distribution signals exist; first maintainer response time still requires timeline-event sampling.
- Search progress: bounded steps stream while the Agent runs and the browser can cancel background
  refinement; server-side detached job resumption is not yet implemented.
- Evaluation: a versioned 40-case constraint suite, 100-case curated relevance suite, and 20-pair
  preference set report Recall@10, nDCG@10, MRR@10, pairwise accuracy, bootstrap bounds, and feature
  ablations. Independent second-annotator review is still absent.
- Observability: Agent traces, request IDs, server timing, path P50/P95 and error rates, plus model
  and embedding call/token/configured-cost metrics exist; version-trend dashboards are not complete.
- Reliability: model and GitHub degradation and per-process public rate limiting are visible;
  distributed rate limiting and broader fault injection remain.

## Not implemented in V1 yet

- GitHub GraphQL batching and OSS Insight integration.
- Redis-backed task queue and a dedicated long-running scheduler service.
- README/CONTRIBUTING section embeddings and pgvector recall.
- MLflow experiment tracking and the required ablation suite.
- GitHub OAuth personalization, private-activity access, profile export, and profile deletion. The
  current matcher deliberately uses only public profile data and requires no account.
- Learning-to-rank training and personalized reranking.
- Admin sync API with authentication.
- Production-like 150-case evaluation gate; the current E2E suite covers core desktop/mobile search
  and navigation but not every detail workflow.
- Demo video and final experiment report.

## Recommended implementation order

1. Add second-annotator review to the relevance and preference suites.
2. Capture timestamped per-channel rankings so RRF lift can be evaluated offline.
3. Add first-response timing from Issue/PR timeline events.
4. Expand production fault-injection checks and distributed rate limiting.
