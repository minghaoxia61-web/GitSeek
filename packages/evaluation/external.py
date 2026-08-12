import math
from datetime import date

from packages.domain.evaluation import EmbeddingEvaluationSummary, EvaluationMetric
from packages.embeddings import EmbeddingAPIError, OpenAIEmbeddingClient
from packages.embeddings.service import cosine_similarity
from packages.retrieval import parse_search_constraints

from .service import _load_retrieval_dataset, build_evaluation_summary


async def evaluate_external_embeddings(
    client: OpenAIEmbeddingClient | None,
) -> EmbeddingEvaluationSummary:
    if client is None:
        return EmbeddingEvaluationSummary(configured=False, status="unavailable")
    dataset = _load_retrieval_dataset()
    repositories = dataset["repositories"]
    queries = [query for intent in dataset["intents"] for query in intent["queries"]]
    repository_texts = [
        "\n".join(
            [
                item["full_name"],
                item["description"],
                " ".join(item["topics"]),
                item["language"],
            ]
        )
        for item in repositories
    ]
    try:
        vectors = await client.embed([*queries, *repository_texts])
    except EmbeddingAPIError:
        return EmbeddingEvaluationSummary(
            configured=True,
            status="failed",
            model=client.model,
        )
    query_vectors = vectors[: len(queries)]
    repository_vectors = vectors[len(queries) :]
    reference_date = date.fromisoformat(dataset["reference_date"])
    recalls: list[float] = []
    ndcgs: list[float] = []
    reciprocal_ranks: list[float] = []
    query_index = 0
    for intent in dataset["intents"]:
        grades = intent["grades"]
        for query in intent["queries"]:
            constraints = parse_search_constraints(query, today=reference_date)
            allowed = {
                item["full_name"]
                for item in repositories
                if (constraints.language == "Any" or item["language"] == constraints.language)
                and (not constraints.licenses or item["license"] in constraints.licenses)
            }
            relevant = {
                name for name, grade in grades.items() if grade > 0 and name in allowed
            }
            if not relevant:
                query_index += 1
                continue
            scored = sorted(
                (
                    (cosine_similarity(query_vectors[query_index], vector), item["full_name"])
                    for item, vector in zip(repositories, repository_vectors, strict=True)
                    if item["full_name"] in allowed
                ),
                reverse=True,
            )[:10]
            names = [name for _, name in scored]
            recalls.append(len(relevant.intersection(names)) / len(relevant))
            dcg = sum(
                (2 ** grades.get(name, 0) - 1) / math.log2(rank + 1)
                for rank, name in enumerate(names, start=1)
            )
            ideal = sorted(
                (grade for name, grade in grades.items() if name in relevant),
                reverse=True,
            )[:10]
            ideal_dcg = sum(
                (2**grade - 1) / math.log2(rank + 1)
                for rank, grade in enumerate(ideal, start=1)
            )
            ndcgs.append(dcg / ideal_dcg if ideal_dcg else 0.0)
            first = next(
                (rank for rank, name in enumerate(names, start=1) if name in relevant),
                None,
            )
            reciprocal_ranks.append(1 / first if first else 0.0)
            query_index += 1
    local_summary = build_evaluation_summary()
    local_ndcg = next(
        metric.value for metric in local_summary.metrics if metric.key == "ndcg_at_10"
    )
    external_ndcg = round(sum(ndcgs) / len(ndcgs) * 100, 1)
    return EmbeddingEvaluationSummary(
        configured=True,
        status="completed",
        model=client.model,
        sample_count=len(recalls),
        metrics=[
            EvaluationMetric(
                key="external_recall_at_10",
                label="External Recall@10",
                value=round(sum(recalls) / len(recalls) * 100, 1),
                unit="%",
                target=85.0,
                passed=sum(recalls) / len(recalls) >= 0.85,
            ),
            EvaluationMetric(
                key="external_ndcg_at_10",
                label="External nDCG@10",
                value=external_ndcg,
                unit="%",
                target=75.0,
                passed=external_ndcg >= 75.0,
            ),
            EvaluationMetric(
                key="external_mrr_at_10",
                label="External MRR@10",
                value=round(sum(reciprocal_ranks) / len(reciprocal_ranks) * 100, 1),
                unit="%",
                target=80.0,
                passed=sum(reciprocal_ranks) / len(reciprocal_ranks) >= 0.8,
            ),
            EvaluationMetric(
                key="external_ndcg_lift",
                label="External embedding lift",
                value=round(external_ndcg - local_ndcg, 1),
                unit="pp",
                target=2.0,
                passed=external_ndcg - local_ndcg >= 2.0,
            ),
        ],
    )
