import asyncio

import httpx

from packages.github_client import GitHubClient, GitHubRateLimitError


def _repository_payload(*, stars: int = 42) -> dict[str, object]:
    return {
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


def test_search_repositories_returns_typed_page_and_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["x-github-api-version"] == "2022-11-28"
        assert request.url.params["q"] == "language:Python"
        return httpx.Response(
            200,
            json={
                "total_count": 1,
                "incomplete_results": False,
                "items": [_repository_payload()],
            },
            headers={
                "etag": '"search-v1"',
                "x-ratelimit-remaining": "29",
                "x-ratelimit-reset": "1785747600",
            },
        )

    async def run() -> None:
        async with GitHubClient(
            token="test-token",
            transport=httpx.MockTransport(handler),
        ) as client:
            page = await client.search_repositories("language:Python")

        assert page.etag == '"search-v1"'
        assert page.rate_limit_remaining == 29
        assert page.result.items[0].license is not None
        assert page.result.items[0].license.spdx_id == "MIT"

    asyncio.run(run())


def test_search_repositories_raises_specific_rate_limit_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "rate limit exceeded"},
            headers={"x-ratelimit-reset": "1785747600"},
        )

    async def run() -> None:
        async with GitHubClient(transport=httpx.MockTransport(handler)) as client:
            try:
                await client.search_repositories("language:Python")
            except GitHubRateLimitError as exc:
                assert exc.reset_at == 1785747600
            else:
                raise AssertionError("expected GitHubRateLimitError")

    asyncio.run(run())

