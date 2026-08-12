import asyncio

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from packages.domain.models import Base, Repository, RepositorySnapshot
from packages.github_client.schemas import GitHubSearchPage
from workers.sync.repositories import RepositorySynchronizer


def _page(*, stars: int) -> GitHubSearchPage:
    return GitHubSearchPage.model_validate(
        {
            "etag": '"seed-page"',
            "rate_limit_remaining": 29,
            "result": {
                "total_count": 1,
                "incomplete_results": False,
                "items": [
                    {
                        "id": 123,
                        "name": "demo",
                        "full_name": "octocat/demo",
                        "owner": {"login": "octocat"},
                        "description": "A test repository",
                        "html_url": "https://github.com/octocat/demo",
                        "default_branch": "main",
                        "language": "Python",
                        "topics": ["fastapi"],
                        "license": {"spdx_id": "MIT"},
                        "stargazers_count": stars,
                        "forks_count": 3,
                        "open_issues_count": 2,
                        "archived": False,
                        "pushed_at": "2026-08-01T12:00:00Z",
                        "created_at": "2025-01-01T12:00:00Z",
                        "updated_at": "2026-08-01T12:00:00Z",
                    }
                ],
            },
        }
    )


class StubGitHubClient:
    def __init__(self, pages: list[GitHubSearchPage]) -> None:
        self._pages = iter(pages)
        self.calls: list[tuple[str, int]] = []

    async def search_repositories(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 100,
        etag: str | None = None,
    ) -> GitHubSearchPage:
        del per_page, etag
        self.calls.append((query, page))
        return next(self._pages)


def test_sync_creates_then_updates_without_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        first_sync = RepositorySynchronizer(session, StubGitHubClient([_page(stars=42)]))
        first_stats = asyncio.run(first_sync.sync_query("language:Python"))

        second_sync = RepositorySynchronizer(session, StubGitHubClient([_page(stars=99)]))
        second_stats = asyncio.run(second_sync.sync_query("language:Python"))

        repositories = list(session.scalars(select(Repository)))

    assert first_stats.created == 1
    assert first_stats.updated == 0
    assert second_stats.created == 0
    assert second_stats.updated == 1
    assert len(repositories) == 1
    assert repositories[0].stars == 99
    assert repositories[0].source_etag == '"seed-page"'


def test_sync_skips_duplicate_metric_snapshots() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        first_sync = RepositorySynchronizer(session, StubGitHubClient([_page(stars=42)]))
        first_stats = asyncio.run(first_sync.sync_query("language:Python"))
        second_sync = RepositorySynchronizer(session, StubGitHubClient([_page(stars=42)]))
        second_stats = asyncio.run(second_sync.sync_query("language:Python"))
        snapshot_count = session.scalar(select(func.count(RepositorySnapshot.id)))

    assert first_stats.snapshots_created == 1
    assert second_stats.snapshots_created == 0
    assert snapshot_count == 1
