from fastapi.testclient import TestClient

from apps.api.main import app
from packages.feedback import feedback_store


def test_feedback_is_acknowledged_and_counted() -> None:
    feedback_store.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/feedback",
            json={"repository": "example/demo", "action": "helpful", "query": "FastAPI"},
        )
        summary = client.get("/api/v1/feedback/summary")

    assert response.status_code == 201
    assert summary.json() == {"total": 1, "by_action": {"helpful": 1}}
