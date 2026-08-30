import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from packages.domain.models import Base
from packages.domain.models.fixer import FixerRunRecord
from workers.agent_runner.runner import claim_next_run, process_run


@pytest.fixture()
def factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _queue_run(factory, *, issue_number=None) -> str:
    with factory() as session:
        run = FixerRunRecord(
            id="run-claim-1",
            repo_full_name="owner/repo",
            issue_number=issue_number,
            status="queued",
        )
        session.add(run)
        session.commit()
        return run.id


def test_claim_marks_running_and_drains_queue(factory):
    run_id = _queue_run(factory)
    assert claim_next_run(factory) == run_id
    with factory() as session:
        assert session.get(FixerRunRecord, run_id).status == "running"
    assert claim_next_run(factory) is None


def test_process_run_marks_missing_issue_as_failed(factory):
    run_id = _queue_run(factory, issue_number=None)
    assert claim_next_run(factory) == run_id
    import asyncio

    asyncio.run(process_run(run_id, session_factory=factory, keep_workspace=True))
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == "failed"
        assert "issue number" in (row.error or "")


def test_process_run_ignores_unknown_run(factory):
    import asyncio

    asyncio.run(process_run("does-not-exist", session_factory=factory))
