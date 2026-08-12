from fastapi.testclient import TestClient

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
    assert 0 <= metrics["recall_at_10"]["value"] <= 100
    assert 0 <= metrics["ndcg_at_10"]["value"] <= 100
    assert 0 <= metrics["mrr_at_10"]["value"] <= 100
    assert metrics["ndcg_at_10"]["value"] >= metrics["keyword_ndcg_at_10"]["value"]
    assert metrics["ndcg_lift"]["value"] >= 0
