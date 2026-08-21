from collections.abc import AsyncIterator, Iterator

from sqlalchemy.orm import Session

from packages.database.session import get_session_factory
from packages.domain.settings import get_settings
from packages.embeddings import OpenAIEmbeddingClient
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
        input_cost_per_million=settings.model_input_cost_per_million,
        output_cost_per_million=settings.model_output_cost_per_million,
    )


async def get_embedding_client() -> AsyncIterator[OpenAIEmbeddingClient | None]:
    settings = get_settings()
    if settings.embedding_api_key is None or not settings.embedding_model:
        yield None
        return
    async with OpenAIEmbeddingClient(
        settings.embedding_api_key,
        model=settings.embedding_model,
        base_url=settings.embedding_api_url,
        cost_per_million=settings.embedding_cost_per_million,
    ) as client:
        yield client
