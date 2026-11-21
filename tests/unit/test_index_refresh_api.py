import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.dependencies import get_db_session, get_github_client
from apps.api.main import app
from packages.domain.models import IndexSyncCursor
from packages.domain.settings import get_settings
from tests.unit.test_repository_sync import StubGitHubClient, _page
from workers.sync.repositories import _select_refresh_cursors


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


def test_refresh_schedule_does_not_starve_overdue_long_tail() -> None:
    now = datetime(2026, 11, 21, tzinfo=UTC)
    cursors = [
        IndexSyncCursor(id=1, query="language:Python stars:>=1000",
                        last_success_at=now - timedelta(days=2)),
        IndexSyncCursor(id=2, query="language:Go stars:>=1000",
                        last_success_at=now - timedelta(days=2)),
        IndexSyncCursor(id=3, query="language:Rust stars:1..9",
                        last_success_at=now - timedelta(days=40)),
    ]
    selected = _select_refresh_cursors(cursors, count=2, now=now)
    assert selected[0].id == 3


@pytest.fixture()
def refresh_session():
    with contextmanager(app.dependency_overrides[get_db_session])() as session:
        yield session


@pytest.fixture()
def refresh_http(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret-at-least-16-characters")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_failed_refresh_is_retryable_and_preserves_new_cursors(refresh_http, refresh_session):
    from packages.github_client import GitHubAPIError

    class FailingGitHub:
        async def search_repositories(self, *args, **kwargs):
            raise GitHubAPIError("upstream unavailable")

    async def override():
        yield FailingGitHub()

    app.dependency_overrides[get_github_client] = override
    response = refresh_http.get(
        "/api/v1/jobs/refresh-index",
        headers={"Authorization": "Bearer test-secret-at-least-16-characters"},
    )
    assert response.status_code == 503
    body = response.json()
    assert len(body["failed_queries"]) == 4
    assert "unknown" not in body["failed_queries"]
    cursors = list(refresh_session.scalars(select(IndexSyncCursor)))
    assert len(cursors) == 24
    assert sum(cursor.failure_count for cursor in cursors) == 4
    assert all(cursor.next_page == 1 and cursor.last_success_at is None for cursor in cursors)


def test_partial_refresh_keeps_success_but_reports_failure(refresh_http, refresh_session):
    from packages.github_client import GitHubAPIError

    class PartialGitHub(StubGitHubClient):
        async def search_repositories(self, query, *, page=1, **kwargs):
            if not self.calls:
                self.calls.append((query, page))
                raise GitHubAPIError("first shard failed")
            return await super().search_repositories(query, page=page, **kwargs)

    github = PartialGitHub([_page(stars=42), _page(stars=43), _page(stars=44)])

    async def override():
        yield github

    app.dependency_overrides[get_github_client] = override
    response = refresh_http.get(
        "/api/v1/jobs/refresh-index",
        headers={"Authorization": "Bearer test-secret-at-least-16-characters"},
    )
    assert response.status_code == 503
    body = response.json()
    assert len(body["failed_queries"]) == 1
    assert body["fetched"] == 3
    assert body["pruned"] == 0
    cursors = list(refresh_session.scalars(select(IndexSyncCursor)))
    assert sum(cursor.last_success_at is not None for cursor in cursors) == 3
    assert sum(cursor.failure_count for cursor in cursors) == 1


def test_refresh_timeout_keeps_pages_for_retry(refresh_session):
    from workers.sync.repositories import refresh_index

    class SlowGitHub:
        async def search_repositories(self, *args, **kwargs):
            await asyncio.Event().wait()

    result = asyncio.run(refresh_index(refresh_session, SlowGitHub(), timeout_s=0.01))
    assert len(result.failed_queries) == 4
    assert result.fetched == 0
    assert result.pruned == 0
    cursors = list(refresh_session.scalars(select(IndexSyncCursor)))
    assert all(cursor.next_page == 1 and cursor.last_success_at is None for cursor in cursors)


def test_refresh_preserves_old_repositories_not_in_this_batch(refresh_http, refresh_session):
    from packages.domain.models import Repository
    from tests.unit.test_repository_index import make_repository

    old = make_repository()
    old.archived = True
    refresh_session.add(old)
    refresh_session.commit()
    github = StubGitHubClient([_page(stars=42)] * 4)

    async def override():
        yield github

    app.dependency_overrides[get_github_client] = override
    response = refresh_http.get(
        "/api/v1/jobs/refresh-index",
        headers={"Authorization": "Bearer test-secret-at-least-16-characters"},
    )
    assert response.status_code == 200
    assert response.json()["pruned"] == 0
    assert refresh_session.scalar(select(Repository).where(Repository.github_id == 101)) is not None
