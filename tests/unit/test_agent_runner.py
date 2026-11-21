import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from packages.agent_core.fixer import FAILURE_TEST_ENVIRONMENT, FixerResult, FixerStepTrace
from packages.domain.models import Base
from packages.domain.models.fixer import FixerPatchRecord, FixerRunRecord, FixerStepRecord
from packages.domain.settings import Settings
from workers.agent_runner import runner
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


@pytest.fixture()
def now(monkeypatch):
    value = datetime.now(UTC)
    monkeypatch.setattr(runner, "datetime", SimpleNamespace(now=lambda tz: value))
    return value


@pytest.fixture()
def offline(monkeypatch, tmp_path):
    settings = Settings.model_construct(
        openai_api_key=SecretStr("test-key"),
        agent_workspace_root=str(tmp_path),
    )
    github = MagicMock()
    github.__aenter__.return_value = github
    github.get_issue = AsyncMock(
        return_value=SimpleNamespace(number=7, title="Fix a bug", body="Expected behavior")
    )
    agent = SimpleNamespace(run=AsyncMock(return_value=FixerResult()))
    replacements = {
        "get_settings": Mock(return_value=settings),
        "workspace_root": Mock(return_value=tmp_path),
        "GitHubClient": Mock(return_value=github),
        "ChatCompletionClient": Mock(return_value=object()),
        "OpenAIEmbeddingClient": Mock(side_effect=AssertionError("unexpected embedding client")),
        "clone_repository": Mock(),
        "enrich_issue": AsyncMock(return_value=SimpleNamespace(search_terms=["bug"])),
        "locate": AsyncMock(
            return_value=[SimpleNamespace(path="module.py", score=1.0, channels=("keyword",))]
        ),
        "create_sandbox": Mock(return_value=object()),
        "FixerAgent": Mock(return_value=agent),
    }
    for name, replacement in replacements.items():
        monkeypatch.setattr(runner, name, replacement)
    return SimpleNamespace(settings=settings, github=github, agent=agent, **replacements)


def _queue_run(factory, *, issue_number=None, run_id="run-claim-1", status="queued", **values):
    with factory() as session:
        run = FixerRunRecord(
            id=run_id,
            repo_full_name="owner/repo",
            issue_number=issue_number,
            status=status,
            **values,
        )
        session.add(run)
        session.commit()
        return run.id


def test_claim_marks_running_and_drains_queue(factory, now):
    run_id = _queue_run(factory, updated_at=now - timedelta(hours=2))
    assert claim_next_run(factory) == run_id
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == "running"
        assert row.started_at.replace(tzinfo=UTC) == now
        assert row.updated_at.replace(tzinfo=UTC) == now
    assert claim_next_run(factory) is None


@pytest.mark.parametrize("has_queued_run", [False, True])
def test_claim_expires_only_running_runs_with_stale_heartbeats(factory, now, has_queued_run):
    old = now - timedelta(hours=2)
    _queue_run(
        factory, run_id="expired", status="running", started_at=old,
        updated_at=now - timedelta(minutes=31),
    )
    _queue_run(
        factory, run_id="recent", status="running", started_at=old,
        updated_at=now - timedelta(minutes=29),
    )
    for status in ("succeeded", "failed"):
        _queue_run(
            factory, run_id=status, status=status, updated_at=old,
            completed_at=old, success=status == "succeeded", error="original error",
        )
    queued_id = _queue_run(factory, updated_at=old) if has_queued_run else None

    assert claim_next_run(factory) == queued_id
    assert claim_next_run(factory) is None  # Abandoned work is never requeued.
    with factory() as session:
        expired = session.get(FixerRunRecord, "expired")
        assert expired.status == "failed"
        assert expired.success is False
        assert expired.failure_category == FAILURE_TEST_ENVIRONMENT
        assert expired.completed_at.replace(tzinfo=UTC) == now
        assert "heartbeat" in expired.error
        assert "30 minutes" in expired.error
        recent = session.get(FixerRunRecord, "recent")
        assert recent.status == "running"
        assert recent.success is None
        assert recent.completed_at is None
        assert recent.error is None
        assert recent.updated_at.replace(tzinfo=UTC) == now - timedelta(minutes=29)
        for status in ("succeeded", "failed"):
            terminal = session.get(FixerRunRecord, status)
            assert terminal.status == status
            assert terminal.success is (status == "succeeded")
            assert terminal.updated_at.replace(tzinfo=UTC) == old
            assert terminal.completed_at.replace(tzinfo=UTC) == old
            assert terminal.error == "original error"


def test_persist_step_refreshes_only_its_run_heartbeat(factory, now):
    old = now - timedelta(minutes=31)
    run_id = _queue_run(factory, status="running", updated_at=old)
    _queue_run(factory, run_id="other", status="running", updated_at=old)
    step = FixerStepTrace(
        seq=1, round=1, tool="bash", input={"command": "pytest"}, output="ok", latency_ms=12,
    )
    asyncio.run(runner._persist_step_factory(factory, run_id)(step))

    with factory() as session:
        assert session.get(FixerRunRecord, run_id).updated_at.replace(tzinfo=UTC) == now
        assert session.get(FixerRunRecord, "other").updated_at.replace(tzinfo=UTC) == old
        saved = session.scalars(select(FixerStepRecord)).one()
        assert (saved.run_id, saved.seq, saved.round, saved.tool) == (run_id, 1, 1, "bash")
        assert saved.input_json == step.input
        assert saved.output == step.output
        assert saved.latency_ms == step.latency_ms
    assert claim_next_run(factory) is None
    with factory() as session:
        assert session.get(FixerRunRecord, run_id).status == "running"
        assert session.get(FixerRunRecord, "other").status == "failed"


def test_process_run_marks_missing_issue_as_failed(factory, offline):
    run_id = _queue_run(factory)
    assert claim_next_run(factory) == run_id
    asyncio.run(process_run(run_id, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == "failed"
        assert row.success is False
        assert row.failure_category == FAILURE_TEST_ENVIRONMENT
        assert row.completed_at is not None
        assert "issue number" in row.error
    offline.GitHubClient.assert_not_called()
    offline.clone_repository.assert_not_called()


@pytest.mark.parametrize("status", [None, "queued", "succeeded", "failed"])
def test_process_run_ignores_unknown_and_nonrunning_runs(factory, offline, status):
    run_id = "does-not-exist"
    if status is not None:
        run_id = _queue_run(factory, status=status)
    asyncio.run(process_run(run_id, session_factory=factory))
    offline.get_settings.assert_not_called()
    offline.workspace_root.assert_not_called()
    offline.GitHubClient.assert_not_called()
    offline.clone_repository.assert_not_called()
    offline.agent.run.assert_not_awaited()
    if status is not None:
        with factory() as session:
            row = session.get(FixerRunRecord, run_id)
            assert row.status == status
            assert row.error is None


@pytest.mark.parametrize(
    "failing_component",
    ["get_settings", "FixerConfig", "workspace_root", "GitHubClient", "ChatCompletionClient",
     "clone_repository", "create_sandbox", "agent_run"],
)
def test_process_run_catches_initialization_and_execution_failures(
    factory, offline, monkeypatch, failing_component,
):
    run_id = _queue_run(factory, issue_number=7)
    assert claim_next_run(factory) == run_id
    error = RuntimeError(f"controlled {failing_component} failure")
    if failing_component == "FixerConfig":
        monkeypatch.setattr(runner, "FixerConfig", Mock(side_effect=error))
    elif failing_component == "agent_run":
        offline.agent.run.side_effect = error
    else:
        getattr(offline, failing_component).side_effect = error

    asyncio.run(process_run(run_id, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == "failed"
        assert row.success is False
        assert row.failure_category == FAILURE_TEST_ENVIRONMENT
        assert row.error == f"RuntimeError: {error}"
        assert row.completed_at is not None
        assert session.scalars(select(FixerPatchRecord)).all() == []


@pytest.mark.parametrize(
    ("success", "test_ok"), [(True, True), (False, True), (False, False), (False, None)],
)
def test_process_run_persists_actual_test_outcome(factory, offline, success, test_ok):
    run_id = _queue_run(factory, issue_number=7)
    assert claim_next_run(factory) == run_id
    result = FixerResult(
        success=success, test_ok=test_ok, diff="controlled patch", summary="controlled result",
        rounds=2, token_in=100, token_out=20, cost_usd=0.01,
        failure_category=None if success else "patch_logic_error",
    )
    offline.agent.run.return_value = result
    asyncio.run(process_run(run_id, session_factory=factory, backend="docker"))

    offline.github.get_issue.assert_awaited_once_with("owner", "repo", 7)
    offline.ChatCompletionClient.assert_called_once()
    offline.clone_repository.assert_called_once()
    workspace = offline.workspace_root.return_value / f"owner__repo-{run_id[:8]}"
    offline.clone_repository.assert_called_once_with("https://github.com/owner/repo.git", workspace)
    offline.create_sandbox.assert_called_once_with("docker", workspace)
    assert offline.FixerAgent.call_args.kwargs["config"].test_command is None
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == ("succeeded" if success else "failed")
        assert row.success is success
        assert row.failure_category == result.failure_category
        assert row.summary == result.summary
        assert (row.rounds, row.token_in, row.token_out, row.cost_usd) == (2, 100, 20, 0.01)
        assert row.completed_at is not None
        assert row.result_json["locator"] == [
            {"path": "module.py", "score": 1.0, "channels": ["keyword"]},
        ]
        patch = session.scalars(select(FixerPatchRecord)).one()
        assert patch.run_id == run_id
        assert patch.round == result.rounds
        assert patch.diff == result.diff
        assert patch.test_ok is test_ok


def test_late_result_does_not_overwrite_expired_run(factory, offline, now):
    run_id = _queue_run(factory, issue_number=7)
    assert claim_next_run(factory) == run_id

    async def finish_after_expiry():
        with factory() as session:
            row = session.get(FixerRunRecord, run_id)
            row.updated_at = now - timedelta(minutes=31)
            session.commit()
        assert claim_next_run(factory) is None
        return FixerResult(success=True, test_ok=True, diff="late patch")

    offline.agent.run.side_effect = finish_after_expiry
    asyncio.run(process_run(run_id, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == "failed"
        assert row.success is False
        assert "heartbeat" in row.error
        assert session.scalars(select(FixerPatchRecord)).all() == []


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_fail_preserves_terminal_results(factory, status, now):
    run_id = _queue_run(
        factory, status=status, success=status == "succeeded", error="original error",
        completed_at=now, failure_category="original category",
    )
    runner._fail(factory, run_id, "late exception")
    with factory() as session:
        row = session.get(FixerRunRecord, run_id)
        assert row.status == status
        assert row.success is (status == "succeeded")
        assert row.error == "original error"
        assert row.failure_category == "original category"
        assert row.completed_at.replace(tzinfo=UTC) == now
