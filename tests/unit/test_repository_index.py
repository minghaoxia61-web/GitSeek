import asyncio
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from packages.domain.models import Base, Repository
from packages.domain.search import SearchRequest
from packages.github_client import GitHubRateLimitError
from packages.retrieval import RepositoryIndex
from packages.search import SearchService


def make_repository() -> Repository:
    return Repository(
        github_id=101,
        full_name="example/fastapi-indexed",
        owner="example",
        name="fastapi-indexed",
        description="FastAPI learning service",
        html_url="https://github.com/example/fastapi-indexed",
        default_branch="main",
        primary_language="Python",
        topics=["fastapi", "education"],
        license_spdx="MIT",
        stars=120,
        forks=8,
        open_issues=4,
        archived=False,
        pushed_at=datetime(2026, 8, 5, tzinfo=UTC),
        github_created_at=datetime(2025, 1, 1, tzinfo=UTC),
        github_updated_at=datetime(2026, 8, 5, tzinfo=UTC),
        fetched_at=datetime(2026, 8, 6, tzinfo=UTC),
        raw_metadata={},
    )


class RateLimitedClient:
    async def search_repositories(self, *args, **kwargs):
        del args, kwargs
        raise GitHubRateLimitError("rate limited")


def test_local_index_returns_results_when_github_is_rate_limited() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(make_repository())
        session.commit()

        response = asyncio.run(
            SearchService(
                RateLimitedClient(),
                repository_index=RepositoryIndex(session),
            ).search(SearchRequest(query="适合学习 FastAPI 的 MIT 项目"))
        )

        assert response.retrieval.github_status == "unavailable"
        assert response.retrieval.local_candidates == 1
        assert response.results[0].full_name == "example/fastapi-indexed"
        assert response.results[0].retrieval_sources == ["local_index"]
        assert response.results[0].data_fetched_at is not None
        assert response.results[0].data_valid_until is not None
        validity = response.results[0].data_valid_until - response.results[0].data_fetched_at
        assert validity.days == 7


def test_index_status_reports_repository_freshness() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(make_repository())
        session.commit()
        status = RepositoryIndex(session).status()

    assert status.ready is True
    assert status.repository_count == 1
    assert status.freshest_at is not None
