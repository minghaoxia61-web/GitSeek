from datetime import date
from uuid import uuid4

from packages.domain.search import SearchRequest, SearchResponse
from packages.github_client import GitHubClient
from packages.persistence import ProductPersistence
from packages.ranking import rank_repositories
from packages.retrieval import build_github_query, parse_search_constraints


class SearchService:
    def __init__(self, client: GitHubClient, persistence: ProductPersistence | None = None) -> None:
        self._client = client
        self._persistence = persistence

    async def search(self, request: SearchRequest, *, today: date | None = None) -> SearchResponse:
        constraints = parse_search_constraints(request.query, today=today)
        if request.purpose is not None:
            constraints.purpose = request.purpose
        if request.weekly_hours is not None:
            constraints.weekly_hours = request.weekly_hours
        if request.platform:
            constraints.platform = request.platform
        if request.project_size:
            constraints.project_size = request.project_size
        if request.licenses is not None:
            constraints.licenses = request.licenses
        if request.pushed_after is not None:
            constraints.pushed_after = request.pushed_after
        github_query = build_github_query(constraints)
        page = await self._client.search_repositories(
            github_query,
            per_page=100,
        )
        results, eligible_count = rank_repositories(
            page.result.items,
            constraints,
            limit=request.limit,
        )
        response = SearchResponse(
            session_id=str(uuid4()),
            query=request.query,
            generated_github_query=github_query,
            constraints=constraints,
            source_total_count=page.result.total_count,
            eligible_candidate_count=eligible_count,
            ranking_version="metadata-baseline-v1",
            results=results,
        )
        if self._persistence is not None:
            self._persistence.save_search(request, response, page.result.items)
        return response
