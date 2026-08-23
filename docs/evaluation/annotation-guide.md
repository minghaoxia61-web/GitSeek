# Retrieval annotation protocol

GitSeek uses versioned relevance judgments rather than treating ranking scores as ground truth. The
current `retrieval-relevance-v2` corpus contains 100 bilingual queries, 23 repositories, and 2,300
query–repository judgments from one primary curator. This guide adds a reproducible second-reviewer
workflow without pretending that independent labels already exist.

## Dataset split

Queries are split by **intent group**, not by individual paraphrase. All ten variants of one intent
stay in the same split, preventing near-duplicate queries from leaking into evaluation.

| Split | Intent groups | Queries | Purpose |
| --- | ---: | ---: | --- |
| Train | 7 | 70 | feature development and qualitative analysis |
| Dev | 1 | 10 | threshold and weight selection |
| Test | 2 | 20 | final reporting only |

The assignment is deterministic and versioned by `gitseek-retrieval-split-v1`.

## Grade scale

- `0`: not relevant; the repository does not satisfy the main need.
- `1`: weakly relevant; related ecosystem or supporting tool, but not a direct answer.
- `2`: relevant; a reasonable answer with some mismatch or missing preference.
- `3`: highly relevant; directly satisfies the requested technology, purpose, and constraints.

Judge relevance, not repository fame. Do not use the existing production rank as a label.

## Second-reviewer workflow

Generate a blind, intent-stratified 30% packet:

```powershell
python -m packages.evaluation.annotations export `
  --annotator reviewer-02 `
  --sample-rate 0.30 `
  --output .local/evaluation/reviewer-02.json
```

The packet intentionally contains `null` grades. The reviewer fills every `grade` with an integer
from 0 to 3 without seeing the primary curator's label. Keep personal names out of the file; use a
stable pseudonymous ID such as `reviewer-02`.

After annotation, validate the packet and generate the agreement/conflict report:

```powershell
python -m packages.evaluation.annotations agreement `
  --annotations .local/evaluation/reviewer-02.json `
  --output .local/evaluation/reviewer-02-agreement.json
```

The report includes exact agreement, unweighted Cohen's Kappa, quadratic-weighted Kappa, and a
conflict list ordered by grade distance. Review all two- or three-grade disagreements first, record
an adjudicated label in the next dataset version, and never silently overwrite either source label.

Inspect the current split and language buckets with:

```powershell
python -m packages.evaluation.annotations profile
```

## Reporting rules

- Continue to describe the dataset as `single-curator` until a completed blind packet is reviewed.
- Report coverage together with Kappa; agreement on a tiny convenience sample is not sufficient.
- Keep the test split untouched while tuning ranking weights.
- State that confidence intervals measure variation inside the fixed corpus, not all of GitHub.
- Increase repository and query coverage through a new version; do not mutate historical labels.

## Expansion target

The next dataset should contain 500–3,000 timestamped repositories and 300–500 queries, with
language, technology, project-size, activity, and contribution-difficulty buckets. At least 20–30%
of queries should receive an independent second review before the new metric is used on a resume.
