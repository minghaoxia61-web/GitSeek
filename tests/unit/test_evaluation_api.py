from fastapi.testclient import TestClient

from apps.api.dependencies import get_embedding_client
from apps.api.main import app


def test_evaluation_endpoint_reports_real_parser_run() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/evals/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 40
    assert payload["dataset_version"] == "parser-constraints-v2"
    assert payload["metrics"][0]["key"] == "constraint_accuracy"
    assert payload["metrics"][0]["value"] >= 95
    assert len(payload["categories"]) == 8
    assert payload["retrieval_dataset_version"] == "retrieval-relevance-v1"
    assert payload["retrieval_case_count"] == 100
    assert payload["relevance_judgment_count"] == 2300
    metrics = {item["key"]: item for item in payload["metrics"]}
    assert metrics["recall_at_10"]["value"] >= 85
    assert metrics["ndcg_at_10"]["value"] >= 75
    assert metrics["mrr_at_10"]["value"] >= 80
    assert metrics["ndcg_at_10"]["value"] >= metrics["keyword_ndcg_at_10"]["value"]
    assert metrics["ndcg_lift"]["value"] >= 0


def test_external_embedding_evaluation_reports_unconfigured_provider() -> None:
    async def no_embedding_client():
        yield None

    app.dependency_overrides[get_embedding_client] = no_embedding_client
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/evals/embeddings")
    finally:
        app.dependency_overrides.pop(get_embedding_client, None)

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "status": "unavailable",
        "model": None,
        "sample_count": 0,
        "metrics": [],
    }


def test_external_embedding_evaluation_runs_fixed_suite() -> None:
    class StubEmbeddingClient:
        model = "test-embedding"

        async def embed(self, inputs: list[str]) -> list[list[float]]:
            return [
                [float((sum(text.encode("utf-8")) + offset) % 17) for offset in range(8)]
                for text in inputs
            ]

    async def embedding_client():
        yield StubEmbeddingClient()

    app.dependency_overrides[get_embedding_client] = embedding_client
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/evals/embeddings")
    finally:
        app.dependency_overrides.pop(get_embedding_client, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["status"] == "completed"
    assert payload["model"] == "test-embedding"
    assert payload["sample_count"] == 100
    assert {item["key"] for item in payload["metrics"]} == {
        "external_recall_at_10",
        "external_ndcg_at_10",
        "external_mrr_at_10",
        "external_ndcg_lift",
    }
