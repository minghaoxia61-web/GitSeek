from datetime import datetime

from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from packages.github_client.schemas import GitHubSearchPage


class StubSearchClient:
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
        assert query.startswith("FastAPI language:Python archived:false pushed:>")
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
    assert payload["ranking_version"] == "hybrid-index-baseline-v1"
    assert payload["retrieval"]["github_candidates"] == 1
    assert payload["results"][0]["retrieval_sources"] == ["github_live"]
    fetched_at = datetime.fromisoformat(payload["results"][0]["data_fetched_at"])
    valid_until = datetime.fromisoformat(payload["results"][0]["data_valid_until"])
    assert (valid_until - fetched_at).days == 7
    assert payload["eligible_candidate_count"] == 1
    assert payload["results"][0]["full_name"] == "example/fastapi-demo"
    assert payload["results"][0]["constraint_match"]["license"] == "MATCH"
