# GitSeek architecture

GitSeek uses a staged recommendation pipeline. Its Agent is a bounded orchestration layer around
deterministic retrieval and evidence collection, so a run remains inspectable and reproducible.

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

The implementation provides the API runtime, repository persistence, a typed GitHub synchronization
path, deterministic ranking and evaluation, and bounded Agent orchestration. Model-assisted query
understanding is optional and remains isolated from hard constraints and factual verification; when
it is unavailable, the same workflow continues with the versioned rule parser.

## Agent run lifecycle

```text
model/rule parse -> plan search -> hybrid retrieval -> investigate Top 1-3 -> verify evidence
     |              |              |                    |                    |
     +--------------+--------------+--------------------+--------------------+
                                persisted trace
```

Each node records timestamps, duration, attempts, status, and a user-readable summary. Repository
investigation runs concurrently with a maximum of three targets and one retry for transient GitHub
errors. Rate limits are not retried. A missing investigation or evidence conflict marks the run as
partial instead of hiding uncertainty. FastAPI persists traces to PostgreSQL; the public Worker uses
the equivalent D1 schema.

The optional model planner calls the OpenAI Responses API once at the beginning of a run and accepts
only a strict query-plan schema. Its output is sanitized before becoming GitHub search text. Explicit
form selections override inferred values, and the model cannot relax later hard filters or execute
tools directly. A missing key, timeout, API error, or invalid response returns to the versioned rule
parser and is visible as a partial run rather than silently producing the same behavior.

## Metadata recommendation baseline

The searchable vertical slice uses a deterministic hybrid pipeline:

```text
Chinese query -> rule-based constraints + free bilingual term expansion
                                      -> local full-text index + GitHub live search
                                              |
                                              v
                                  merge/dedupe -> hard filters -> metadata score -> Top 10
```

Language, license, archive state, and activity date are hard constraints. A candidate with missing
or conflicting evidence is excluded instead of letting a soft relevance score override the user's
request. The ranking score uses only fields returned by repository search and labels itself
`hybrid-vector-v5`; it blends deterministic metadata scoring with a cached local semantic vector and
does not claim that README, tests, or contribution instructions exist before investigation.
Common intents are expanded locally into up to three GitHub terms before live retrieval. This keeps
the deterministic fast path precise without an LLM or external embeddings request; model-planned
terms can still replace those expansions during the optional refinement path.
Each result carries its retrieval sources and fetch time. When GitHub is unavailable or rate-limited,
the same hard-filter and ranking path can operate on the synchronized index alone.

Agent searches may request an external semantic ranker. Query and repository text are embedded in
batches through an OpenAI-compatible embeddings endpoint, then blended with the same deterministic
metadata score. Repository vectors are stored by model and content hash; only new or changed content
is embedded again. Provider errors never bypass hard filters: the request falls back to
`hybrid-vector-v5`, while successful external ranking is identified as `hybrid-external-vector-v6`.
The language model planner and embedding provider use separate credentials and endpoints.

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
system explain when GitHub activity happened and when GitSeek last verified it. Search response
ETags and rate-limit metadata are exposed by the client so later scheduler work can add conditional
requests without changing the domain model.
