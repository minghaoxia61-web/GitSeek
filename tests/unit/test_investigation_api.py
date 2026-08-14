from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from tests.unit.test_investigation import StubInvestigationClient


async def override_github_client():
    yield StubInvestigationClient()


class CountingInvestigationClient(StubInvestigationClient):
    def __init__(self) -> None:
        self.repository_calls = 0

    async def get_repository(self, owner: str, repo: str):
        self.repository_calls += 1
        return await super().get_repository(owner, repo)


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


def test_investigation_endpoint_reuses_cached_dossier() -> None:
    github = CountingInvestigationClient()

    async def override():
        yield github

    app.dependency_overrides[get_github_client] = override
    try:
        with TestClient(app) as client:
            first = client.get("/api/v1/repos/example/demo/investigate")
            second = client.get("/api/v1/repos/example/demo/investigate")
            refreshed = client.get("/api/v1/repos/example/demo/investigate?refresh=true")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == second.status_code == refreshed.status_code == 200
    assert github.repository_calls == 2
