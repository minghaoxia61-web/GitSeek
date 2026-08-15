from datetime import UTC, datetime, timedelta
from typing import Literal

from packages.domain.search import SearchConstraints, TrendingResponse
from packages.github_client import GitHubClient
from packages.ranking import rank_repositories
from packages.retrieval import build_github_query


class TrendingService:
    """Build a recent-popularity ranking from an explicitly stars-sorted candidate pool."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    async def list(
        self,
        *,
        days: Literal[7, 30],
        limit: int,
        now: datetime | None = None,
    ) -> TrendingResponse:
        fetched_at = now or datetime.now(UTC)
        reference_date = fetched_at.date()
        pushed_after = reference_date - timedelta(days=days)
        constraints = SearchConstraints(pushed_after=pushed_after)
        github_query = build_github_query(constraints, [])
        page = await self._client.search_repositories(
            github_query,
            per_page=100,
            sort="stars",
            order="desc",
        )
        results, _ = rank_repositories(
            page.result.items,
            constraints,
            limit=limit,
            now=fetched_at,
        )
        for result in results:
            result.retrieval_sources = ["github_live"]
            result.data_fetched_at = fetched_at
            result.data_valid_until = fetched_at + timedelta(minutes=15)
        return TrendingResponse(
            range_days=days,
            generated_github_query=github_query,
            results=results,
            fetched_at=fetched_at,
        )
