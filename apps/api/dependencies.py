from collections.abc import AsyncIterator, Iterator

from sqlalchemy.orm import Session

from packages.database.session import get_session_factory
from packages.domain.settings import get_settings
from packages.github_client import GitHubClient
from packages.model_planning import OpenAIQueryPlanner


async def get_github_client() -> AsyncIterator[GitHubClient]:
    settings = get_settings()
    async with GitHubClient(
        token=settings.github_token,
        base_url=settings.github_api_url,
        api_version=settings.github_api_version,
    ) as client:
        yield client


def get_db_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session


def get_query_planner() -> OpenAIQueryPlanner | None:
    settings = get_settings()
    if settings.openai_api_key is None:
        return None
    return OpenAIQueryPlanner(
        settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        base_url=settings.openai_api_url,
    )
