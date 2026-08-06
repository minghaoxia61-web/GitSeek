# OpenScout architecture

OpenScout uses a staged recommendation pipeline. The initial implementation deliberately starts
with a deterministic vertical slice before introducing embeddings or agent orchestration.

```text
natural-language query
        |
        v
constraint parsing
        |
        v
candidate retrieval -> hard filters -> deterministic ranking
                                      |
                                      v
                              evidence-backed Top 10
```

The first two implementation milestones provide the API runtime, repository persistence, and a
typed GitHub synchronization path. Subsequent milestones add deterministic ranking, evaluation,
and finally bounded LLM assistance.

## Metadata recommendation baseline

The searchable vertical slice uses a deterministic hybrid pipeline:

```text
Chinese query -> rule-based constraints -> local full-text index + GitHub live search
                                              |
                                              v
                                  merge/dedupe -> hard filters -> metadata score -> Top 10
```

Language, license, archive state, and activity date are hard constraints. A candidate with missing
or conflicting evidence is excluded instead of letting a soft relevance score override the user's
request. The ranking score uses only fields returned by repository search and labels itself
`hybrid-index-baseline-v1`; it does not claim that README, tests, or contribution instructions exist.
Each result carries its retrieval sources and fetch time. When GitHub is unavailable or rate-limited,
the same hard-filter and ranking path can operate on the synchronized index alone.

## On-demand repository investigation

Repository detail requests use a bounded, read-only evidence workflow:

```text
repository metadata
  + community profile
  + root file listing
  + workflow listing
  + README markers
        |
        v
engineering signals -> deterministic scores -> evidence dossier
```

The workflow does not clone repositories, install dependencies, or follow instructions contained in
repository text. Each positive or negative signal carries a source URL, fetch timestamp, and confidence
level. Root-directory absence is presented as a limitation rather than proof that a nested artifact
does not exist.

## Data freshness contract

Repository rows keep GitHub timestamps separately from `fetched_at`. This distinction lets the
system explain when GitHub activity happened and when OpenScout last verified it. Search response
ETags and rate-limit metadata are exposed by the client so later scheduler work can add conditional
requests without changing the domain model.
