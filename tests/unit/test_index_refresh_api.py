from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from apps.api.routes.jobs import _select_refresh_cursors
from packages.domain.models import IndexSyncCursor
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
    github = StubGitHubClient(
        [_page(stars=42), _page(stars=43), _page(stars=44), _page(stars=45)]
    )

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
    assert len(payload["queries"]) == 4
    assert payload["fetched"] == 4
    assert payload["created"] == 1
    assert payload["updated"] == 3
    assert payload["snapshots_created"] == 4
    assert payload["failed_queries"] == []
    assert payload["pruned"] == 0
    assert [page for _, page in github.calls] == [1, 1, 1, 1]


def test_refresh_schedule_prioritizes_due_popular_shards() -> None:
    now = datetime(2026, 8, 14, tzinfo=UTC)
    cursors = [
        IndexSyncCursor(
            id=1,
            query="language:Python archived:false stars:>=1000",
            last_success_at=now - timedelta(days=2),
        ),
        IndexSyncCursor(
            id=2,
            query="language:Python archived:false stars:100..999",
            last_success_at=now - timedelta(hours=12),
        ),
        IndexSyncCursor(
            id=3,
            query="language:Python archived:false stars:10..99",
            last_success_at=now - timedelta(days=8),
        ),
    ]

    selected = _select_refresh_cursors(cursors, count=2, now=now)

    assert [cursor.id for cursor in selected] == [1, 3]
