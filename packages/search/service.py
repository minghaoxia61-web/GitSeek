import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from packages.domain.search import (
    RetrievalSummary,
    SearchConstraints,
    SearchRequest,
    SearchResponse,
)
from packages.embeddings import EmbeddingAPIError, ExternalEmbeddingService
from packages.github_client import GitHubAPIError, GitHubClient
from packages.persistence import ProductPersistence
from packages.ranking import rank_repositories
from packages.retrieval import (
    RepositoryIndex,
    build_github_queries,
    infer_github_terms,
    parse_search_constraints,
)

LOCAL_RANKING_VERSION = "hybrid-vector-v4"
EXTERNAL_RANKING_VERSION = "hybrid-external-vector-v5"


class SearchService:
    def __init__(
        self,
        client: GitHubClient,
        persistence: ProductPersistence | None = None,
        repository_index: RepositoryIndex | None = None,
        embedding_service: ExternalEmbeddingService | None = None,
    ) -> None:
        self._client = client
        self._persistence = persistence
        self._repository_index = repository_index
        self._embedding_service = embedding_service

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
        effective_search_terms = (
            search_terms if search_terms is not None else infer_github_terms(request.query)
        )
        github_queries = build_github_queries(
            constraints,
            effective_search_terms,
        )[: request.live_query_limit]
        github_query = " | ".join(github_queries)
        external_requested = request.embedding_mode == "external"
        expected_ranking_version = (
            EXTERNAL_RANKING_VERSION
            if external_requested and self._embedding_service is not None
            else LOCAL_RANKING_VERSION
        )
        if self._persistence is not None:
            cached = self._persistence.load_cached_search(
                request.query,
                constraints,
                github_query,
                expected_ranking_version,
                limit=request.limit,
            )
            if cached is not None:
                return cached
        indexed = []
        if self._repository_index is not None:
            keyword_indexed = self._repository_index.search(request.query, constraints)
            semantic_indexed = self._repository_index.semantic_search(request.query, constraints)
            indexed_by_name = {
                item.repository.full_name: item for item in [*keyword_indexed, *semantic_indexed]
            }
            indexed = list(indexed_by_name.values())
        github_items_by_name = {}
        github_total = 0
        github_status = "live"
        successful_queries = 0
        last_error: GitHubAPIError | None = None
        query_results = await asyncio.gather(
            *(self._client.search_repositories(query, per_page=30) for query in github_queries),
            return_exceptions=True,
        )
        for query_result in query_results:
            if isinstance(query_result, GitHubAPIError):
                last_error = query_result
                continue
            if isinstance(query_result, Exception):
                raise query_result
            successful_queries += 1
            github_total += query_result.result.total_count
            for item in query_result.result.items:
                github_items_by_name[item.full_name] = item
        github_items = list(github_items_by_name.values())
        if successful_queries == 0:
            if not indexed:
                assert last_error is not None
                raise last_error
            github_status = "unavailable"

        candidates = {item.repository.full_name: item.repository for item in indexed}
        sources = {item.repository.full_name: {"local_index"} for item in indexed}
        fetched_at = {item.repository.full_name: item.fetched_at for item in indexed}
        for item in github_items:
            candidates[item.full_name] = item
            sources.setdefault(item.full_name, set()).add("github_live")
            fetched_at[item.full_name] = datetime.now(UTC)
        embedding_status = "local"
        embedding_model = None
        embedding_cached = 0
        embedding_generated = 0
        semantic_scores = None
        ranking_version = LOCAL_RANKING_VERSION
        if external_requested:
            if self._embedding_service is None:
                embedding_status = "unavailable"
            else:
                try:
                    embedding_result = await self._embedding_service.similarities(
                        request.query,
                        list(candidates.values()),
                    )
                    semantic_scores = embedding_result.scores
                    embedding_status = "external"
                    embedding_model = embedding_result.model
                    embedding_cached = embedding_result.cached_repositories
                    embedding_generated = embedding_result.embedded_repositories
                    ranking_version = EXTERNAL_RANKING_VERSION
                except EmbeddingAPIError:
                    embedding_status = "unavailable"
        results, eligible_count = rank_repositories(
            list(candidates.values()),
            constraints,
            limit=request.limit,
            query=" ".join([request.query, *effective_search_terms]),
            semantic_scores=semantic_scores,
        )
        for result in results:
            result.retrieval_sources = sorted(sources.get(result.full_name, set()))
            result.data_fetched_at = fetched_at.get(result.full_name)
            if result.data_fetched_at is not None:
                result.data_valid_until = result.data_fetched_at + timedelta(days=7)
        response = SearchResponse(
            session_id=str(uuid4()),
            query=request.query,
            generated_github_query=github_query,
            constraints=constraints,
            source_total_count=github_total or len(indexed),
            eligible_candidate_count=eligible_count,
            ranking_version=ranking_version,
            results=results,
            retrieval=RetrievalSummary(
                local_candidates=len(indexed),
                github_candidates=len(github_items),
                github_status=github_status,
                index_freshest_at=max(
                    (item.fetched_at for item in indexed),
                    default=None,
                ),
                embedding_status=embedding_status,
                embedding_model=embedding_model,
                embedding_cached_repositories=embedding_cached,
                embedding_generated_repositories=embedding_generated,
            ),
        )
        if self._persistence is not None:
            saved = self._persistence.save_search(request, response, github_items)
            if not saved:
                response.retrieval.persistence_status = "unavailable"
                response.retrieval.persistence_error = self._persistence.last_error
        return response
