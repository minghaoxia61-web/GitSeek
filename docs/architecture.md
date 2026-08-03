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

The first searchable vertical slice uses a deterministic pipeline:

```text
Chinese query -> rule-based constraints -> GitHub query -> hard filters -> metadata score -> Top 10
```

Language, license, archive state, and activity date are hard constraints. A candidate with missing
or conflicting evidence is excluded instead of letting a soft relevance score override the user's
request. The ranking score uses only fields returned by repository search and labels itself
`metadata-baseline-v1`; it does not claim that README, tests, or contribution instructions exist.

## Data freshness contract

Repository rows keep GitHub timestamps separately from `fetched_at`. This distinction lets the
system explain when GitHub activity happened and when OpenScout last verified it. Search response
ETags and rate-limit metadata are exposed by the client so later scheduler work can add conditional
requests without changing the domain model.
