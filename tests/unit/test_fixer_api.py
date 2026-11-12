import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.dependencies import get_db_session
from apps.api.main import app
from packages.domain.models import Base
from packages.domain.models.fixer import FixerPatchRecord, FixerRunRecord, FixerStepRecord


@pytest.fixture()
def runner_factory(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("apps.api.routes.fixer._get_factory", lambda: factory)

    def override_db_session():
        with factory() as session:
            yield session

    # Re-point the DI session at the same engine so API tests and SSE snapshots agree.
    app.dependency_overrides[get_db_session] = override_db_session
    yield factory
    app.dependency_overrides.pop(get_db_session, None)
    Base.metadata.drop_all(engine)
    engine.dispose()


def seed_terminal_run(factory) -> str:
    run_id = "run-1"
    with factory() as session:
        session.add(
            FixerRunRecord(
                id=run_id,
                repo_full_name="owner/repo",
                issue_number=7,
                status="succeeded",
                model="stub-model",
                max_rounds=3,
                token_budget=1000,
                rounds=2,
                token_in=120,
                token_out=60,
                cost_usd=0.002,
                success=True,
                summary="fixed",
            )
        )
        session.add(
            FixerStepRecord(
                run_id=run_id,
                seq=1,
                round=1,
                tool="run_bash",
                input_json={"command": "pytest -q"},
                output="exit=0\n1 passed",
                latency_ms=15,
            )
        )
        session.add(FixerPatchRecord(run_id=run_id, round=2, diff="--- a/x.py\n+++ b/x.py"))
        session.commit()
    return run_id


def test_create_run_queues_and_resolves_issue_number_from_url():
    client = TestClient(app)
    response = client.post(
        "/api/v1/fixer/runs",
        json={"repo_full_name": "owner/repo", "issue_url": "https://github.com/owner/repo/issues/42"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["issue_number"] == 42
    assert payload["run_id"]


def test_create_run_requires_issue_reference():
    client = TestClient(app)
    response = client.post("/api/v1/fixer/runs", json={"repo_full_name": "owner/repo"})
    assert response.status_code == 422


def test_create_run_rejects_bad_repo_name():
    client = TestClient(app)
    response = client.post(
        "/api/v1/fixer/runs",
        json={"repo_full_name": "not-a-repo", "issue_number": 1},
    )
    assert response.status_code == 422


def test_get_run_and_diff(runner_factory):
    run_id = seed_terminal_run(runner_factory)
    client = TestClient(app)
    payload = client.get(f"/api/v1/fixer/runs/{run_id}").json()
    assert payload["status"] == "succeeded"
    assert payload["verification"] is None  # Historical success has no verification evidence.
    assert payload["cost_usd"] is None  # Historical numeric defaults have no pricing receipt.
    assert payload["step_count"] == 1
    diff = client.get(f"/api/v1/fixer/runs/{run_id}/diff").json()
    assert "b/x.py" in diff["diff"]


def test_get_missing_run_returns_404():
    client = TestClient(app)
    assert client.get("/api/v1/fixer/runs/nope").status_code == 404
    assert client.get("/api/v1/fixer/runs/nope/diff").status_code == 404


def test_database_outage_returns_visible_503():
    """DB outage must surface as a clear 503, not a bare 500 browsers read as a network error."""
    from sqlalchemy.exc import OperationalError

    from apps.api.dependencies import get_db_session

    def broken_session():
        raise OperationalError("CONNECT", {}, Exception("password authentication failed"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db_session] = broken_session
    try:
        client = TestClient(app)
        response = client.get("/api/v1/fixer/runs/some-run")
        assert response.status_code == 503
        assert "数据库" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_stream_emits_steps_then_result(runner_factory):
    run_id = seed_terminal_run(runner_factory)
    client = TestClient(app)
    events: list[str] = []
    with client.stream("GET", f"/api/v1/fixer/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event: ") or line.startswith("data: "):
                events.append(line)
    names = [line.split(": ", 1)[1] for line in events if line.startswith("event: ")]
    assert "open" in names
    assert "step" in names
    assert names[-1] == "result"
    data_lines = [line.split(": ", 1)[1] for line in events if line.startswith("data: ")]
    final = json.loads(data_lines[-1])
    assert final["status"] == "succeeded"


def test_stream_reports_missing_run(runner_factory):
    client = TestClient(app)
    events: list[str] = []
    with client.stream("GET", "/api/v1/fixer/runs/ghost/stream") as response:
        for line in response.iter_lines():
            if line.startswith("event: "):
                events.append(line)
    assert events[-1] == "event: error"


def test_timeline_returns_steps_then_obeys_after_seq(runner_factory):
    run_id = seed_terminal_run(runner_factory)
    client = TestClient(app)
    first = client.get(f"/api/v1/fixer/runs/{run_id}/timeline").json()
    assert first["run"]["status"] == "succeeded"
    assert len(first["steps"]) == 1
    assert first["steps"][0]["tool"] == "run_bash"
    assert "b/x.py" in first["run"]["diff"]
    second = client.get(f"/api/v1/fixer/runs/{run_id}/timeline", params={"after_seq": 1}).json()
    assert second["steps"] == []
    assert client.get("/api/v1/fixer/runs/ghost/timeline").status_code == 404


def test_api_exposes_stored_verification_in_run_and_timeline(runner_factory):
    run_id = seed_terminal_run(runner_factory)
    verification = {
        "version": "fixer-verification-v1", "scope": "workspace_tests",
        "model_finished": True, "patch_present": True, "apply_ok": True,
        "test_executed": True, "test_ok": False, "test_exit_code": 7,
        "test_timed_out": False,
    }
    with runner_factory() as session:
        run = session.get(FixerRunRecord, run_id)
        run.result_json = {"verification": verification}
        run.status = "failed"
        run.success = False
        session.commit()
    client = TestClient(app)
    assert client.get(f"/api/v1/fixer/runs/{run_id}").json()["verification"] == verification
    timeline = client.get(f"/api/v1/fixer/runs/{run_id}/timeline").json()
    assert timeline["run"]["verification"] == verification


def test_public_create_cannot_set_trusted_test_command(runner_factory):
    client = TestClient(app)
    response = client.post("/api/v1/fixer/runs", json={
        "repo_full_name": "owner/repo", "issue_number": 1,
        "test_command": "echo untrusted-command",
    })
    assert response.status_code == 200
    with runner_factory() as session:
        assert session.get(FixerRunRecord, response.json()["run_id"]).test_command is None


def test_api_returns_independent_acceptance_evidence(runner_factory):
    run_id = seed_terminal_run(runner_factory)
    acceptance = {"version": "clean-acceptance-v1", "passed": False,
                  "baseline_target": {"exit_code": 1}, "baseline_reproduced": True}
    with runner_factory() as session:
        run = session.get(FixerRunRecord, run_id)
        run.result_json = {"acceptance": acceptance}
        session.commit()
    client = TestClient(app)
    assert client.get(f"/api/v1/fixer/runs/{run_id}").json()["acceptance"] == acceptance
    timeline = client.get(f"/api/v1/fixer/runs/{run_id}/timeline").json()
    assert timeline["run"]["acceptance"] == acceptance


def test_api_cost_comes_from_billing_receipt_not_legacy_numeric_column(runner_factory):
    run_id = seed_terminal_run(runner_factory)
    bill = {"version": "provider-billing-v1", "state": "unknown",
            "estimated_cost_usd": None, "known_cost_subtotal_usd": 0.002}
    with runner_factory() as session:
        run = session.get(FixerRunRecord, run_id)
        run.result_json = {"billing": bill}
        session.commit()
    payload = TestClient(app).get(f"/api/v1/fixer/runs/{run_id}").json()
    assert payload["cost_usd"] is None
    assert payload["billing"] == bill
