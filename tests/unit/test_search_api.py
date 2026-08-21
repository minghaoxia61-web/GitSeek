from datetime import datetime

from fastapi.testclient import TestClient

from apps.api.dependencies import get_embedding_client, get_github_client
from apps.api.main import app
from packages.github_client.schemas import GitHubSearchPage


class StubSearchClient:
    def __init__(self) -> None:
        self.calls = 0

    async def search_repositories(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 100,
        etag: str | None = None,
        sort: str | None = None,
        order: str = "desc",
    ) -> GitHubSearchPage:
        del page, per_page, etag, sort, order
        self.calls += 1
        normalized_query = query.casefold()
        assert normalized_query.startswith("fastapi")
        assert "language:python" in normalized_query
        assert "archived:false" in normalized_query
        return GitHubSearchPage.model_validate(
            {
                "result": {
                    "total_count": 1,
                    "incomplete_results": False,
                    "items": [
                        {
                            "id": 1,
                            "name": "fastapi-demo",
                            "full_name": "example/fastapi-demo",
                            "owner": {"login": "example"},
                            "description": "A FastAPI learning project",
                            "html_url": "https://github.com/example/fastapi-demo",
                            "default_branch": "main",
                            "language": "Python",
                            "topics": ["fastapi"],
                            "license": {"spdx_id": "MIT"},
                            "stargazers_count": 100,
                            "forks_count": 10,
                            "open_issues_count": 4,
                            "archived": False,
                            "pushed_at": "2026-08-01T00:00:00Z",
                            "created_at": "2025-01-01T00:00:00Z",
                            "updated_at": "2026-08-01T00:00:00Z",
                        }
                    ],
                }
            }
        )


class StubTrendingClient:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    async def search_repositories(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 100,
        etag: str | None = None,
        sort: str | None = None,
        order: str = "desc",
    ) -> GitHubSearchPage:
        self.request = {
            "query": query,
            "page": page,
            "per_page": per_page,
            "etag": etag,
            "sort": sort,
            "order": order,
        }
        return GitHubSearchPage.model_validate(
            {
                "result": {
                    "total_count": 1,
                    "incomplete_results": False,
                    "items": [
                        {
                            "id": 2,
                            "name": "popular-project",
                            "full_name": "example/popular-project",
                            "owner": {"login": "example"},
                            "description": "A popular and actively maintained project",
                            "html_url": "https://github.com/example/popular-project",
                            "default_branch": "main",
                            "language": "Python",
                            "topics": ["open-source"],
                            "license": {"spdx_id": "MIT"},
                            "stargazers_count": 50000,
                            "forks_count": 1000,
                            "open_issues_count": 20,
                            "archived": False,
                            "pushed_at": datetime.now().astimezone().isoformat(),
                            "created_at": "2020-01-01T00:00:00Z",
                            "updated_at": datetime.now().astimezone().isoformat(),
                        }
                    ],
                }
            }
        )


async def override_github_client():
    yield StubSearchClient()


def test_search_endpoint_returns_explainable_baseline() -> None:
    app.dependency_overrides[get_github_client] = override_github_client
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/search",
                json={
                    "query": (
                        "找一个适合 Python 初学者学习 FastAPI 的项目，"
                        "MIT 许可证，最近半年有更新"
                    )
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ranking_version"] == "hybrid-rrf-v11"
    assert payload["retrieval"]["github_candidates"] == 1
    assert payload["retrieval"]["fusion_strategy"] == "rrf"
    assert payload["retrieval"]["channel_candidate_counts"]["github_live_1"] == 1
    assert payload["retrieval"]["total_latency_ms"] >= 0
    assert payload["results"][0]["retrieval_sources"] == ["github_live"]
    fetched_at = datetime.fromisoformat(payload["results"][0]["data_fetched_at"])
    valid_until = datetime.fromisoformat(payload["results"][0]["data_valid_until"])
    assert (valid_until - fetched_at).days == 7
    assert payload["eligible_candidate_count"] == 1
    assert payload["results"][0]["full_name"] == "example/fastapi-demo"
    assert payload["results"][0]["constraint_match"]["license"] == "MATCH"


def test_trending_endpoint_requests_a_stars_sorted_candidate_pool() -> None:
    github = StubTrendingClient()

    async def override_trending_client():
        yield github

    app.dependency_overrides[get_github_client] = override_trending_client
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/trending?days=7&limit=6")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300, s-maxage=900"
    assert github.request is not None
    assert github.request["sort"] == "stars"
    assert github.request["order"] == "desc"
    assert github.request["per_page"] == 100
    assert "archived:false" in str(github.request["query"])
    assert "pushed:>" in str(github.request["query"])
    assert response.json()["results"][0]["full_name"] == "example/popular-project"


def test_equivalent_search_uses_recent_database_cache() -> None:
    github = StubSearchClient()

    async def override_counted_client():
        yield github

    app.dependency_overrides[get_github_client] = override_counted_client
    request = {
        "query": "FastAPI Python MIT learning project updated recently",
        "limit": 1,
        "purpose": "learning",
        "live_query_limit": 1,
    }
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/search", json=request)
            second = client.post("/api/v1/search", json=request)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert github.calls == 1
    assert first.json()["retrieval"]["cache_hit"] is False
    assert second.json()["retrieval"]["cache_hit"] is True
    assert second.json()["retrieval"]["cached_at"] is not None
    assert second.json()["results"] == first.json()["results"]


def test_external_embedding_mode_reranks_with_configured_provider() -> None:
    class StubEmbeddingClient:
        model = "test-embedding"

        async def embed(self, inputs: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in inputs]

    async def embedding_client():
        yield StubEmbeddingClient()

    app.dependency_overrides[get_github_client] = override_github_client
    app.dependency_overrides[get_embedding_client] = embedding_client
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/search",
                json={
                    "query": "FastAPI Python project",
                    "limit": 1,
                    "live_query_limit": 1,
                    "embedding_mode": "external",
                },
            )
    finally:
        app.dependency_overrides.pop(get_github_client, None)
        app.dependency_overrides.pop(get_embedding_client, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ranking_version"] == "hybrid-external-rrf-v12"
    assert payload["retrieval"]["embedding_status"] == "external"
    assert payload["retrieval"]["embedding_model"] == "test-embedding"
