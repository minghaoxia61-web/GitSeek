# Retrieval and reranking experiment v2

Date: 2026-08-23

Dataset: `retrieval-relevance-v2`

Preference set: `retrieval-pairs-v1` (`single-curator`)

Ranking version: `hybrid-rrf-v12`

## Question

Can GitSeek improve relevance over a metadata-only baseline while preserving deterministic hard
constraints and explainability?

## Protocol

- 100 bilingual queries across 10 repository-discovery intents.
- 23 fixed candidate repositories and 2,300 query-document judgments.
- Query-specific grades for the two held-out channel-evaluation intents, with intent grades as a
  fallback for the remaining queries.
- Recall@10, nDCG@10, MRR@10, and 20 curated pairwise preferences.
- A deterministic 95% bootstrap interval using seed `20260821` and 1,000 resamples.

Run the experiment through `POST /api/v1/evals/run` or `build_evaluation_summary()`.

## Results

| Variant | Recall@10 | nDCG@10 | MRR@10 |
| --- | ---: | ---: | ---: |
| Metadata-only baseline | 58.5% | 38.8% | 37.1% |
| Full feature reranker | 97.5% | 91.0% | 96.1% |
| Without popularity | 97.8% | 91.7% | 96.6% |
| Without activity | 97.5% | 91.0% | 96.1% |

Additional gates:

- nDCG@10 95% bootstrap lower bound: **88.0%**
- Pairwise preference accuracy: **85.0%**
- nDCG@10 lift over metadata-only baseline: **+52.2 percentage points**

## Decision

Popularity remains capped at 5 points as a weak trust signal. The no-popularity ablation is 0.7
nDCG points higher on this small corpus, but removing the feature globally would overfit a
single-curator dataset. The production configuration therefore keeps the bounded feature and
publishes the ablation result instead of hiding the tradeoff.

Query-expansion terms are used for recall only. The final reranker scores the user's original query,
which prevents generated terms from biasing one repository family. A lexical-or-semantic intent
gate preserves strongly related candidates that do not literally contain expansion terms.

## Limitations

- The relevance set has one primary curator; it is a regression suite, not general search proof.
- The candidate corpus is intentionally small and does not represent all of GitHub.
- Confidence intervals quantify query sampling variation inside this dataset, not domain shift.
- Metrics from v1 and v2 are not directly comparable because v2 corrects held-out labels from
  intent-level grades to query-level grades.
