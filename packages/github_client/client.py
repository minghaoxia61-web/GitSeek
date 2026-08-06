from types import TracebackType

import httpx
from pydantic import SecretStr

from packages.github_client.schemas import (
    GitHubCommunityProfile,
    GitHubContentItem,
    GitHubIssue,
    GitHubRepository,
    GitHubSearchPage,
    GitHubSearchResult,
)


class GitHubAPIError(RuntimeError):
    pass


class GitHubRateLimitError(GitHubAPIError):
    def __init__(self, message: str, *, reset_at: int | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class GitHubNotFoundError(GitHubAPIError):
    pass


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class GitHubClient:
    def __init__(
        self,
        *,
        token: SecretStr | str | None = None,
        base_url: str = "https://api.github.com",
        api_version: str = "2026-03-10",
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": api_version,
            "User-Agent": "OpenScout/0.1.0",
        }
        token_value = token.get_secret_value() if isinstance(token, SecretStr) else token
        if token_value:
            headers["Authorization"] = f"Bearer {token_value}"

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

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
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        if page < 1:
            raise ValueError("page must be at least 1")

        headers = {"If-None-Match": etag} if etag else None
        params: dict[str, str | int] = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "order": order,
        }
        if sort:
            params["sort"] = sort
        response = await self._client.get(
            "/search/repositories",
            params=params,
            headers=headers,
        )

        reset_at = _parse_optional_int(response.headers.get("x-ratelimit-reset"))
        if response.status_code in {403, 429}:
            raise GitHubRateLimitError(
                "GitHub API rate limit exceeded",
                reset_at=reset_at,
            )
        if response.status_code == 304:
            raise GitHubAPIError("GitHub returned 304 but no cached payload was supplied")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubAPIError(f"GitHub API request failed with {response.status_code}") from exc

        result = GitHubSearchResult.model_validate(response.json())
        return GitHubSearchPage(
            result=result,
            etag=response.headers.get("etag"),
            rate_limit_remaining=_parse_optional_int(
                response.headers.get("x-ratelimit-remaining")
            ),
            rate_limit_reset=reset_at,
        )

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> object:
        response = await self._client.get(path, params=params)
        reset_at = _parse_optional_int(response.headers.get("x-ratelimit-reset"))
        if response.status_code in {403, 429}:
            raise GitHubRateLimitError("GitHub API rate limit exceeded", reset_at=reset_at)
        if response.status_code == 404:
            raise GitHubNotFoundError(f"GitHub resource not found: {path}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubAPIError(f"GitHub API request failed with {response.status_code}") from exc
        return response.json()

    async def get_repository(self, owner: str, repo: str) -> GitHubRepository:
        payload = await self._get_json(f"/repos/{owner}/{repo}")
        return GitHubRepository.model_validate(payload)

    async def get_community_profile(self, owner: str, repo: str) -> GitHubCommunityProfile:
        payload = await self._get_json(f"/repos/{owner}/{repo}/community/profile")
        return GitHubCommunityProfile.model_validate(payload)

    async def list_repository_contents(
        self,
        owner: str,
        repo: str,
        *,
        path: str = "",
        ref: str | None = None,
    ) -> list[GitHubContentItem]:
        endpoint = f"/repos/{owner}/{repo}/contents"
        if path:
            endpoint = f"{endpoint}/{path.strip('/')}"
        params = {"ref": ref} if ref else None
        payload = await self._get_json(endpoint, params=params)
        if not isinstance(payload, list):
            raise GitHubAPIError(f"Expected a directory listing for {endpoint}")
        return [GitHubContentItem.model_validate(item) for item in payload]

    async def get_readme(self, owner: str, repo: str) -> GitHubContentItem:
        payload = await self._get_json(f"/repos/{owner}/{repo}/readme")
        return GitHubContentItem.model_validate(payload)

    async def list_repository_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 100,
    ) -> list[GitHubIssue]:
        payload = await self._get_json(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": per_page, "sort": "updated"},
        )
        if not isinstance(payload, list):
            raise GitHubAPIError("Expected an issue listing")
        return [GitHubIssue.model_validate(item) for item in payload]
