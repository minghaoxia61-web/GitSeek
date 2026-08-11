from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from packages.domain.settings import get_settings
from tests.unit.test_repository_sync import StubGitHubClient, _page


def test_scheduled_index_refresh_rejects_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("CRON_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/jobs/refresh-index",
                headers={"Authorization": "Bearer "},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503


def test_scheduled_index_refresh_requires_secret_and_syncs(monkeypatch) -> None:
    monkeypatch.setenv("CRON_SECRET", "test-secret-at-least-16-characters")
    get_settings.cache_clear()
    github = StubGitHubClient([_page(stars=42), _page(stars=43)])

    async def override_github_client():
        yield github

    app.dependency_overrides[get_github_client] = override_github_client
    try:
        with TestClient(app) as client:
            unauthorized = client.get("/api/v1/jobs/refresh-index")
            response = client.get(
                "/api/v1/jobs/refresh-index",
                headers={"Authorization": "Bearer test-secret-at-least-16-characters"},
            )
    finally:
        get_settings.cache_clear()

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["queries"]) == 2
    assert payload["fetched"] == 2
    assert payload["created"] == 1
    assert payload["updated"] == 1
