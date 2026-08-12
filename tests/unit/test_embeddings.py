import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from packages.domain.models import Base, Repository, RepositoryEmbedding
from packages.embeddings import ExternalEmbeddingService, OpenAIEmbeddingClient
from packages.github_client.schemas import GitHubRepository


def _github_repository() -> GitHubRepository:
    return GitHubRepository.model_validate(
        {
            "id": 91,
            "name": "workflow-demo",
            "full_name": "example/workflow-demo",
            "owner": {"login": "example"},
            "description": "Workflow orchestration and scheduler",
            "html_url": "https://github.com/example/workflow-demo",
            "language": "Python",
            "topics": ["workflow", "scheduler"],
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 42,
            "open_issues_count": 3,
            "archived": False,
            "pushed_at": "2026-08-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-08-01T00:00:00Z",
        }
    )


def _repository_record() -> Repository:
    item = _github_repository()
    return Repository(
        github_id=item.id,
        full_name=item.full_name,
        owner=item.owner.login,
        name=item.name,
        description=item.description,
        html_url=item.html_url,
        default_branch="main",
        primary_language=item.language,
        topics=item.topics,
        license_spdx="MIT",
        stars=item.stargazers_count,
        forks=0,
        open_issues=item.open_issues_count,
        archived=False,
        pushed_at=item.pushed_at,
        github_created_at=item.created_at,
        github_updated_at=item.updated_at,
        fetched_at=datetime.now(UTC),
        raw_metadata={},
    )


def test_openai_embedding_client_orders_batch_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "model": "test-embedding",
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
            },
        )

    async def run() -> list[list[float]]:
        async with OpenAIEmbeddingClient(
            "secret",
            model="test-embedding",
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.embed(["query", "repository"])

    assert asyncio.run(run()) == [[1.0, 0.0], [0.0, 1.0]]


def test_repository_embeddings_are_reused_by_content_hash() -> None:
    class StubClient:
        model = "test-embedding"

        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        async def embed(self, inputs: list[str]) -> list[list[float]]:
            self.batch_sizes.append(len(inputs))
            return [[1.0, 0.0] for _ in inputs]

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    embedding_client = StubClient()
    with Session(engine) as session:
        session.add(_repository_record())
        session.commit()
        service = ExternalEmbeddingService(session, embedding_client)  # type: ignore[arg-type]
        first = asyncio.run(service.similarities("工作流调度", [_github_repository()]))
        second = asyncio.run(service.similarities("工作流调度", [_github_repository()]))
        stored = session.scalar(select(RepositoryEmbedding))

    assert first.embedded_repositories == 1
    assert second.cached_repositories == 1
    assert embedding_client.batch_sizes == [2, 1]
    assert stored is not None
    assert stored.model == "test-embedding"
    assert stored.dimensions == 2
