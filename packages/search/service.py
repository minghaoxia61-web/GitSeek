from datetime import UTC, date, datetime
from uuid import uuid4

from packages.domain.search import (
    RetrievalSummary,
    SearchConstraints,
    SearchRequest,
    SearchResponse,
)
from packages.github_client import GitHubAPIError, GitHubClient
from packages.persistence import ProductPersistence
from packages.ranking import rank_repositories
from packages.retrieval import RepositoryIndex, build_github_query, parse_search_constraints


class SearchService:
    def __init__(
        self,
        client: GitHubClient,
        persistence: ProductPersistence | None = None,
        repository_index: RepositoryIndex | None = None,
    ) -> None:
        self._client = client
        self._persistence = persistence
        self._repository_index = repository_index

    async def search(
        self,
        request: SearchRequest,
        *,
        today: date | None = None,
        constraints: SearchConstraints | None = None,
        search_terms: list[str] | None = None,
    ) -> SearchResponse:
        constraints = (
            constraints.model_copy(deep=True)
            if constraints is not None
            else parse_search_constraints(request.query, today=today)
        )
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
        github_query = build_github_query(constraints, search_terms)
        indexed = (
            self._repository_index.search(request.query, constraints)
            if self._repository_index is not None
            else []
        )
        github_items = []
        github_total = 0
        github_status = "live"
        try:
            page = await self._client.search_repositories(
                github_query,
                per_page=100,
            )
            github_items = page.result.items
            github_total = page.result.total_count
        except GitHubAPIError:
            if not indexed:
                raise
            github_status = "unavailable"

        candidates = {item.repository.full_name: item.repository for item in indexed}
        sources = {item.repository.full_name: {"local_index"} for item in indexed}
        fetched_at = {item.repository.full_name: item.fetched_at for item in indexed}
        for item in github_items:
            candidates[item.full_name] = item
            sources.setdefault(item.full_name, set()).add("github_live")
            fetched_at[item.full_name] = datetime.now(UTC)
        results, eligible_count = rank_repositories(
            list(candidates.values()),
            constraints,
            limit=request.limit,
        )
        for result in results:
            result.retrieval_sources = sorted(sources.get(result.full_name, set()))
            result.data_fetched_at = fetched_at.get(result.full_name)
        response = SearchResponse(
            session_id=str(uuid4()),
            query=request.query,
            generated_github_query=github_query,
            constraints=constraints,
            source_total_count=github_total or len(indexed),
            eligible_candidate_count=eligible_count,
            ranking_version="hybrid-index-baseline-v1",
            results=results,
            retrieval=RetrievalSummary(
                local_candidates=len(indexed),
                github_candidates=len(github_items),
                github_status=github_status,
                index_freshest_at=max(
                    (item.fetched_at for item in indexed),
                    default=None,
                ),
            ),
        )
        if self._persistence is not None:
            self._persistence.save_search(request, response, github_items)
        return response
