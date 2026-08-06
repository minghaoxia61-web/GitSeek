from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from packages.domain.models import (
    Base,
    RecommendationRecord,
    Repository,
    RepositorySnapshot,
    SearchSession,
)
from packages.domain.search import (
    Recommendation,
    SearchConstraints,
    SearchRequest,
    SearchResponse,
)
from packages.github_client.schemas import GitHubRepository
from packages.persistence import ProductPersistence


def test_search_results_and_repository_snapshot_are_persisted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = GitHubRepository.model_validate(
        {
            "id": 7,
            "name": "demo",
            "full_name": "example/demo",
            "owner": {"login": "example"},
            "description": "A persisted FastAPI repository",
            "html_url": "https://github.com/example/demo",
            "default_branch": "main",
            "language": "Python",
            "topics": ["fastapi"],
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 42,
            "forks_count": 3,
            "open_issues_count": 2,
            "archived": False,
            "pushed_at": "2026-08-05T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-08-05T00:00:00Z",
        }
    )
    response = SearchResponse(
        session_id="00000000-0000-0000-0000-000000000007",
        query="FastAPI MIT",
        generated_github_query="FastAPI language:Python archived:false",
        constraints=SearchConstraints(technologies=["FastAPI"], licenses=["MIT"]),
        source_total_count=1,
        eligible_candidate_count=1,
        ranking_version="metadata-baseline-v1",
        results=[
            Recommendation(
                rank=1,
                full_name=repository.full_name,
                description=repository.description,
                html_url=repository.html_url,
                score=88.0,
                stars=42,
                language="Python",
                license_spdx="MIT",
                pushed_at=datetime(2026, 8, 5, tzinfo=UTC),
                constraint_match={"language": "MATCH", "license": "MATCH"},
                score_breakdown={"relevance": 35.0},
                reasons=["匹配 FastAPI"],
                risks=[],
            )
        ],
    )

    with Session(engine) as session:
        saved = ProductPersistence(session).save_search(
            SearchRequest(query="FastAPI MIT"),
            response,
            [repository],
        )
        assert saved is True
        assert session.scalar(select(func.count(Repository.id))) == 1
        assert session.scalar(select(func.count(RepositorySnapshot.id))) == 1
        assert session.scalar(select(func.count(SearchSession.id))) == 1
        assert session.scalar(select(func.count(RecommendationRecord.id))) == 1
