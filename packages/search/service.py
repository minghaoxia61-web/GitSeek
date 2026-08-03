from datetime import date

from packages.domain.search import SearchRequest, SearchResponse
from packages.github_client import GitHubClient
from packages.ranking import rank_repositories
from packages.retrieval import build_github_query, parse_search_constraints


class SearchService:
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    async def search(self, request: SearchRequest, *, today: date | None = None) -> SearchResponse:
        constraints = parse_search_constraints(request.query, today=today)
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
        return SearchResponse(
            query=request.query,
            generated_github_query=github_query,
            constraints=constraints,
            source_total_count=page.result.total_count,
            eligible_candidate_count=eligible_count,
            ranking_version="metadata-baseline-v1",
            results=results,
        )

