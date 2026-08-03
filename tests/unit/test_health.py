from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "openscout-api",
        "version": "0.1.0",
        "environment": "local",
    }

