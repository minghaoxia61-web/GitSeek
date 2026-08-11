import asyncio

from packages.domain.search import SearchRequest
from packages.github_client.schemas import GitHubSearchPage
from packages.search import SearchService


class ConcurrentSearchClient:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.per_page_values: list[int] = []

    async def search_repositories(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 100,
        **kwargs,
    ) -> GitHubSearchPage:
        del query, page, kwargs
        self.per_page_values.append(per_page)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        self.active -= 1
        return GitHubSearchPage.model_validate(
            {
                "result": {
                    "total_count": 0,
                    "incomplete_results": False,
                    "items": [],
                }
            }
        )


def test_search_runs_github_queries_concurrently_with_bounded_pages() -> None:
    client = ConcurrentSearchClient()
    response = asyncio.run(
        SearchService(client).search(SearchRequest(query="FastAPI PostgreSQL Redis 项目"))
    )

    assert response.generated_github_query.count(" | ") == 2
    assert client.max_active == 3
    assert client.per_page_values == [30, 30, 30]


def test_fast_search_limits_live_query_fanout() -> None:
    client = ConcurrentSearchClient()
    response = asyncio.run(
        SearchService(client).search(
            SearchRequest(query="FastAPI PostgreSQL Redis 项目", live_query_limit=1)
        )
    )

    assert " | " not in response.generated_github_query
    assert client.max_active == 1
    assert client.per_page_values == [30]
