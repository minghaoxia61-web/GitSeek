# Retrieval channel and RRF experiment v2

Date: 2026-08-23

Snapshot: `test-split-2026-08-23-labels-v2-r4`

Dataset: `retrieval-relevance-v2` test split

Ranking version: `hybrid-rrf-v12`

## Question

What does each local recall channel contribute, and does the final reranker preserve recalled
relevant repositories without overfitting to query-expansion terms?

## Protocol

- The deterministic intent-level test split contains 20 queries from two held-out intent groups.
- Query-level grade overrides replace the overly broad v1 intent-level labels, with the original
  intent grades retained as a fallback.
- Each query runs through production keyword recall, local semantic recall, RRF (`k=60`), and the
  final reranker against the fixed 23-repository corpus.
- The checked-in snapshot is captured in offline mode, so GitHub availability cannot change it.
- Metrics are Recall@10, nDCG@10, and MRR@10 against graded judgments; grades 2-3 count as relevant
  for binary Recall and MRR, while nDCG retains all positive grades.

## Results

| Variant | Recall@10 | nDCG@10 | MRR@10 |
| --- | ---: | ---: | ---: |
| Local keyword | 82.5% | 62.9% | 68.4% |
| Local semantic | 97.5% | 93.1% | 97.5% |
| RRF fusion | 100.0% | 89.8% | 95.0% |
| Final reranker | 100.0% | 94.0% | 97.5% |

RRF increases Recall@10 by **2.5 percentage points** over the strongest single channel but reduces
nDCG@10 by **3.3 points** because the broad keyword channel adds weaker candidates near the top.
The final reranker recovers **4.2 nDCG points** over RRF, preserves 100% Recall@10, and finishes
**0.9 nDCG points** above the strongest single channel.

## Changes driven by diagnostics

- Added a general data-analysis/scientific-computing semantic bridge, raising semantic-channel
  Recall@10 from 88.3% to 97.5% on the corrected v2 labels.
- Replaced the expansion-term hard filter with a lexical-or-semantic intent gate, so semantically
  recalled candidates are not discarded merely because they do not contain `pandas` or `polars`.
- Separated retrieval expansion terms from the final reranker query. Expansion terms now improve
  recall without contaminating relevance scores.
- Added score breakdowns to snapshots and an explicit offline capture mode.

The corrected v2 baseline initially had four actionable diagnostics. After the ranking changes,
one medium-severity ordering diagnostic remains: for “Python 表格数据分析框架”, NumPy and pandas
score within 0.18 points and NumPy appears first. This is retained as a known limitation rather than
forcing a global weight change to fit one query.

## Limitations

- Labels come from one primary curator; query-level overrides improve granularity but are not an
  independent annotation round.
- The candidate corpus is small and cannot establish general GitHub-search quality.
- The checked-in result measures two local channels. GitHub live recall is observable in production
  but intentionally disabled for this reproducible snapshot.
- RRF improves coverage here, not ordering by itself; claims should report both Recall and nDCG.

Reproduce the snapshot and report:

```powershell
.\.venv\Scripts\python -m packages.evaluation.channels live-capture `
  --snapshot-id test-split-2026-08-23-labels-v2-r4 `
  --split test --offline `
  --output packages/evaluation/datasets/retrieval-channels-local-v2.json

.\.venv\Scripts\python -m packages.evaluation.channels evaluate `
  --snapshot packages/evaluation/datasets/retrieval-channels-local-v2.json
```
