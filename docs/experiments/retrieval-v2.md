# Retrieval and reranking experiment v2

Date: 2026-08-21  
Dataset: `retrieval-relevance-v1`  
Preference set: `retrieval-pairs-v1` (`single-curator`)  
Ranking version: `hybrid-rrf-v11`

## Question

Can GitSeek improve relevance over a metadata-only baseline while preserving deterministic hard
constraints and explainability?

## Protocol

- 100 bilingual queries across 10 repository-discovery intents.
- 23 fixed candidate repositories and 2,300 query-document judgments.
- Recall@10, nDCG@10, MRR@10, and 20 curated pairwise preferences.
- A deterministic 95% bootstrap interval using seed `20260821` and 1,000 resamples.
- The same reference date and candidate corpus are used for every ablation.

Run the experiment through `POST /api/v1/evals/run` or `build_evaluation_summary()`.

## Results

| Variant | Recall@10 | nDCG@10 | MRR@10 |
| --- | ---: | ---: | ---: |
| Metadata-only baseline | 54.5% | 38.3% | 40.1% |
| Full feature reranker | 87.3% | 89.3% | 96.6% |
| Without popularity | 87.7% | 90.0% | 97.1% |
| Without activity | 87.3% | 89.3% | 96.6% |

Additional gates:

- nDCG@10 95% bootstrap lower bound: **86.5%**
- Pairwise preference accuracy: **85.0%**
- nDCG@10 lift over metadata-only baseline: **+51.0 percentage points**

## Decision

The original popularity feature allowed repository fame to act as a relevance proxy. Removing it
improved nDCG@10 from 88.2% to 90.0%. GitSeek therefore reduced the maximum popularity contribution
from 15 points to 5 points. The resulting production profile reaches 89.3% nDCG@10 and improves
pairwise accuracy from 80.0% to 85.0%, while retaining a weak trust signal and deterministic
star-count tie-breaking.

## RRF scope

Production search now applies reciprocal-rank fusion to local full-text, local semantic, and each
GitHub live query channel. RRF has unit and API integration coverage. It is not included in the
offline nDCG claim above because the fixed dataset does not preserve independent channel result
lists; claiming an RRF lift from that corpus would be misleading. A future dataset should capture
per-channel rankings from timestamped production snapshots.

## Limitations

- The relevance set has one primary curator; pairwise labels are not yet independently adjudicated.
- The candidate corpus is intentionally small and does not represent all of GitHub.
- Confidence intervals quantify query sampling variation inside this dataset, not domain shift.
- Public-profile Issue matching is heuristic and must not be interpreted as a developer assessment.
