from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable

from packages.domain.models import Base, Repository, RepositoryFeature


def test_repository_schema_can_be_created_in_memory() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    table_names = set(Base.metadata.tables)
    assert table_names == {
        "agent_runs",
        "agent_steps",
        "contribution_issues",
        "feedback",
        "index_sync_cursors",
        "recommendations",
        "repositories",
        "repository_features",
        "repository_embeddings",
        "repository_snapshots",
        "saved_repositories",
        "search_sessions",
    }


def test_feature_evidence_fields_are_nullable() -> None:
    compiled = str(CreateTable(RepositoryFeature.__table__).compile())

    assert RepositoryFeature.__table__.c.has_readme.nullable is True
    assert RepositoryFeature.__table__.c.has_tests.nullable is True
    assert "FOREIGN KEY(repo_id)" in compiled
    assert Repository.__table__.c.github_id.unique is True
