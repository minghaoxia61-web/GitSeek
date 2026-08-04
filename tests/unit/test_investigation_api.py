from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from tests.unit.test_investigation import StubInvestigationClient


async def override_github_client():
    yield StubInvestigationClient()


def test_investigation_endpoint_returns_evidence_dossier() -> None:
    app.dependency_overrides[get_github_client] = override_github_client
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/repos/example/demo/investigate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["full_name"] == "example/demo"
    assert payload["signals"]["has_ci"] is True
    assert payload["scores"]["engineering"] == 100
    assert payload["evidence"][0]["id"] == "community-health"

