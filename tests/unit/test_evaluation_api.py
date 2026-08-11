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
