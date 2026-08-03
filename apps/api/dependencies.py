from collections.abc import AsyncIterator

from packages.domain.settings import get_settings
from packages.github_client import GitHubClient


async def get_github_client() -> AsyncIterator[GitHubClient]:
    settings = get_settings()
    async with GitHubClient(
        token=settings.github_token,
        base_url=settings.github_api_url,
        api_version=settings.github_api_version,
    ) as client:
        yield client

