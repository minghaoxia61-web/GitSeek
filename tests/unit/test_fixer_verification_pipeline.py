import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from packages.agent_core import bench
from packages.agent_core.execution import local_runtime_identity
from packages.agent_core.fixer import FixerResult
from packages.agent_core.ingestion import clone_repository
from packages.agent_core.llm import AgentLLMError
from packages.domain.models import Base
from packages.domain.models.fixer import (
    AgentCodeChunkRecord,
    FixerPatchRecord,
    FixerRunRecord,
    FixerStepRecord,
)
from packages.domain.settings import Settings
from packages.sandbox import LocalSandbox
from tests.unit.test_clean_acceptance import acceptance_protocol
from tests.unit.test_execution_identity import create_history, git
from tests.unit.test_fixer_agent import StubChat
from workers.agent_runner import runner


@pytest.fixture()
def pipeline(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="stub-key",
        EMBEDDING_API_KEY=None,
        agent_workspace_root=str(tmp_path / "workspaces"),
    )
    patch = (
        "--- a/src/auth.py\n+++ b/src/auth.py\n"
        "@@ -1,2 +1,2 @@\n def login_user(token):\n-    return token\n+    return bool(token)\n"
    )
    chat = StubChat([f"```diff\n{patch}```", "FINISH: fixed"])
    source = tmp_path / "source"
    base, _, lock_sha = create_history(source)
    execution = {
        "dataset_version": "test-issues-v1",
        "base_commit": base,
        "environment": {
            "backend": "local",
            "runtime_sha256": local_runtime_identity()["runtime_sha256"],
        },
        "dependency_lock": {"path": "requirements.lock", "sha256": lock_sha},
        "acceptance": acceptance_protocol(),
    }

    class GitHub:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get_issue(self, *args):
            return SimpleNamespace(number=1, title="Boolean return needed", body="Fix login")

    def clone(url, workspace, *, base_commit=None):
        return clone_repository(source.as_uri(), workspace, base_commit=base_commit or base)

    async def enrich(analysis, *args, **kwargs):
        return analysis

    async def locate(*args, **kwargs):
        return []

    monkeypatch.setattr(runner, "GitHubClient", GitHub)
    monkeypatch.setattr(runner, "ChatCompletionClient", lambda *args, **kwargs: chat)
    monkeypatch.setattr(runner, "clone_repository", clone)
    monkeypatch.setattr(runner, "enrich_issue", enrich)
    monkeypatch.setattr(runner, "locate", locate)
    monkeypatch.setattr(
        runner, "create_sandbox", lambda backend, workspace: LocalSandbox(workspace)
    )
    monkeypatch.setattr(bench, "get_settings", lambda: settings)
    yield factory, settings, execution
    assert all("EVALUATOR_ONLY" not in str(messages) for messages in chat.received_messages)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.mark.parametrize(
    "test_command,success,category",
    [
        ("grep -q 'return bool(token)' src/auth.py", True, None),
        ("exit 7", False, "patch_logic_error"),
        (None, False, "test_not_configured"),
    ],
)
def test_worker_persists_separate_patch_and_test_evidence(
    pipeline,
    test_command,
    success,
    category,
):
    factory, settings, _ = pipeline
    with factory() as session:
        session.add(
            FixerRunRecord(
                id="run", repo_full_name="owner/repo", issue_number=1, test_command=test_command
            )
        )
        session.commit()
    assert runner.claim_next_run(factory, run_id="run") == "run"
    asyncio.run(runner.process_run("run", settings=settings, session_factory=factory))
    with factory() as session:
        run = session.get(FixerRunRecord, "run")
        patch = session.execute(
            select(FixerPatchRecord)
            .order_by(
                FixerPatchRecord.created_at.desc(),
                FixerPatchRecord.id.desc(),
            )
            .limit(1)
        ).scalar_one()
        steps = (
            session.execute(select(FixerStepRecord).order_by(FixerStepRecord.seq)).scalars().all()
        )
        assert run.success is success, (
            run.error,
            run.failure_category,
            run.result_json,
            [(step.tool, step.output) for step in steps],
        )
        assert run.status == ("succeeded" if success else "failed")
        assert run.failure_category == category
        assert patch.apply_ok is True
        assert patch.test_ok is (None if test_command is None else success)
        verification = run.result_json["verification"]
        assert verification["model_finished"] is True
        assert verification["patch_present"] is True
        assert verification["test_executed"] is (test_command is not None)
        tests = [step for step in steps if step.tool == "run_tests"]
        assert len(tests) == (0 if test_command is None else 1)
        if tests:
            assert tests[0].input_json["command"] == test_command
            assert verification["test_exit_code"] == (0 if success else 7)


def test_manifest_reaches_worker_and_benchmark_without_claiming_other_tasks(pipeline, tmp_path):
    factory, _, execution = pipeline
    with factory() as session:
        session.add(FixerRunRecord(id="unrelated", repo_full_name="other/repo", issue_number=2))
        session.commit()
    manifest = tmp_path / "manifest.json"
    command = "grep -q 'return bool(token)' src/auth.py"
    manifest.write_text(
        json.dumps(
            [
                {
                    "instance_id": "repo-1",
                    "repo": "owner/repo",
                    "issue_number": 1,
                    "gold_files": ["src/auth.py"],
                    "test_command": command,
                    "execution": execution,
                }
            ]
        ),
        encoding="utf-8",
    )
    report = asyncio.run(
        bench.run_benchmark(
            manifest, session_factory=factory, output_dir=tmp_path / "results", backend="local"
        )
    )
    instance = report["instances"][0]
    assert instance["success"] is True, instance
    assert instance["test_command"] == command
    assert instance["verification"]["test_exit_code"] == 0
    assert instance["execution"]["actual_commit"] == execution["base_commit"]
    assert instance["execution"]["final_commit"] == execution["base_commit"]
    assert instance["execution"]["index_source_commit"] == execution["base_commit"]
    assert report["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert report["metrics"]["e2e_success"] == 100.0
    assert report["verification_scope"] == "clean_checkout_tests"
    assert report["independent_acceptance"] is True
    assert report["local_development_instances"] == 1
    assert instance["acceptance"]["baseline_target"]["exit_code"] == 1
    assert instance["acceptance"]["final_target"]["exit_code"] == 0
    assert len(list((tmp_path / "results").glob("*.json"))) == 1
    with factory() as session:
        assert session.get(FixerRunRecord, "unrelated").status == "queued"


def test_benchmark_does_not_trust_success_without_verification(pipeline, tmp_path, monkeypatch):
    factory, _, execution = pipeline
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "instance_id": "repo-1",
                    "repo": "owner/repo",
                    "issue_number": 1,
                    "test_command": "pytest -q",
                    "execution": execution,
                }
            ]
        ),
        encoding="utf-8",
    )

    async def legacy_worker(run_id, **kwargs):
        with factory() as session:
            run = session.get(FixerRunRecord, run_id)
            run.status = "succeeded"
            run.success = True
            session.add(
                FixerPatchRecord(
                    run_id=run_id, diff="--- a/a.py\n+++ b/a.py\n", apply_ok=True, test_ok=True
                )
            )
            session.commit()

    monkeypatch.setattr(bench, "process_run", legacy_worker)
    report = asyncio.run(
        bench.run_benchmark(manifest, session_factory=factory, output_dir=tmp_path / "results")
    )
    assert report["instances"][0]["success"] is False
    assert report["metrics"]["e2e_success"] == 0.0


@pytest.mark.parametrize("mismatch", ["lock", "runtime", "backend"])
def test_execution_identity_mismatch_stops_before_model_calls(pipeline, monkeypatch, mismatch):
    factory, settings, execution = pipeline
    execution = copy.deepcopy(execution)
    if mismatch == "lock":
        execution["dependency_lock"]["sha256"] = "0" * 64
    elif mismatch == "runtime":
        execution["environment"]["runtime_sha256"] = "0" * 64
    with factory() as session:
        session.add(
            FixerRunRecord(
                id="mismatch",
                repo_full_name="owner/repo",
                issue_number=1,
                execution_spec={"spec": execution},
                test_command="pytest -q",
            )
        )
        session.commit()

    def no_model(*args, **kwargs):
        pytest.fail("identity mismatch must stop before constructing the model client")

    monkeypatch.setattr(runner, "ChatCompletionClient", no_model)
    assert runner.claim_next_run(factory, run_id="mismatch") == "mismatch"
    asyncio.run(
        runner.process_run(
            "mismatch",
            settings=settings,
            session_factory=factory,
            backend="docker" if mismatch == "backend" else None,
        )
    )
    with factory() as session:
        row = session.get(FixerRunRecord, "mismatch")
        assert row.status == "failed"
        assert row.success is False
        assert row.failure_category == "execution_identity_error"
        assert row.result_json["execution"]["identity_verified"] is False
        assert row.result_json["execution"]["requested"]["spec"] == execution


def test_pinned_locator_uses_checked_out_code_and_keeps_shared_index(pipeline, monkeypatch):
    factory, settings, execution = pipeline
    with factory() as session:
        session.add(
            AgentCodeChunkRecord(
                repo_full_name="owner/repo",
                path="src/auth.py",
                name="login_user",
                kind="function",
                content="def login_user(token): return bool(token)",
            )
        )
        session.add(
            FixerRunRecord(
                id="isolated-index",
                repo_full_name="owner/repo",
                issue_number=1,
                execution_spec={"spec": execution},
                test_command="grep -q 'return bool(token)' src/auth.py",
            )
        )
        session.commit()

    async def inspect_locator(session, index_key, issue_text, **kwargs):
        from packages.agent_core.locator import locate

        assert index_key == "fixer-run:isolated-index"
        chunks = (
            session.execute(
                select(AgentCodeChunkRecord).where(
                    AgentCodeChunkRecord.repo_full_name == index_key,
                )
            )
            .scalars()
            .all()
        )
        assert chunks
        assert all("bool(token)" not in chunk.content for chunk in chunks)
        return await locate(session, index_key, issue_text, search_terms=["login_user"])

    monkeypatch.setattr(runner, "locate", inspect_locator)
    assert runner.claim_next_run(factory, run_id="isolated-index") == "isolated-index"
    asyncio.run(runner.process_run("isolated-index", settings=settings, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, "isolated-index")
        assert row.success is True, row.error
        assert row.result_json["locator"][0]["path"] == "src/auth.py"
        chunks = session.execute(select(AgentCodeChunkRecord)).scalars().all()
        assert len(chunks) == 1
        assert chunks[0].repo_full_name == "owner/repo"
        assert "bool(token)" in chunks[0].content


def test_worker_rejects_head_changed_during_agent_execution(pipeline, monkeypatch):
    factory, settings, execution = pipeline
    with factory() as session:
        session.add(
            FixerRunRecord(
                id="changed-head",
                repo_full_name="owner/repo",
                issue_number=1,
                execution_spec={"spec": execution},
                test_command="pytest -q",
            )
        )
        session.commit()

    class ChangingAgent:
        def __init__(self, *, sandbox, **kwargs):
            self.workspace = sandbox.workspace

        async def run(self):
            git(
                self.workspace,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "unexpected version change",
            )
            return FixerResult(success=True)

    monkeypatch.setattr(runner, "FixerAgent", ChangingAgent)
    assert runner.claim_next_run(factory, run_id="changed-head") == "changed-head"
    asyncio.run(runner.process_run("changed-head", settings=settings, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, "changed-head")
        assert row.success is False
        assert row.failure_category == "execution_identity_error"
        assert "HEAD" in row.error


def test_passing_baseline_stops_before_model_and_persists_evidence(pipeline, monkeypatch):
    factory, settings, execution = pipeline
    execution = copy.deepcopy(execution)
    artifact = execution["acceptance"]["files"][0]
    artifact["content"] = artifact["content"].replace(
        "self.assertIs(type(login_user('yes')), bool)",
        "self.assertTrue(login_user('yes'))",
    )
    artifact["sha256"] = hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest()
    with factory() as session:
        session.add(
            FixerRunRecord(
                id="passing-baseline",
                repo_full_name="owner/repo",
                issue_number=1,
                execution_spec={"spec": execution},
                test_command="pytest -q",
            )
        )
        session.commit()

    def no_model(*args, **kwargs):
        pytest.fail("already-passing baseline must stop before model construction")

    monkeypatch.setattr(runner, "ChatCompletionClient", no_model)
    assert runner.claim_next_run(factory, run_id="passing-baseline") == "passing-baseline"
    asyncio.run(runner.process_run("passing-baseline", settings=settings, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, "passing-baseline")
        assert row.status == "failed"
        assert row.success is False
        assert row.failure_category == "baseline_not_reproduced"
        assert row.result_json["acceptance"]["baseline_target"]["exit_code"] == 0
        assert row.token_in == 0


def test_model_failure_after_patch_retains_usage_diff_and_local_receipts(pipeline, monkeypatch):
    factory, settings, _ = pipeline
    settings = settings.model_copy(
        update={"fixer_input_cost_per_million": 1, "fixer_output_cost_per_million": 2}
    )
    patch = (
        "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,2 +1,2 @@\n"
        " def login_user(token):\n-    return token\n+    return bool(token)\n"
    )

    class FailingChat(StubChat):
        async def complete(self, *args, **kwargs):
            if self.calls:
                raise AgentLLMError("provider timeout")
            return await super().complete(*args, **kwargs)

    monkeypatch.setattr(
        runner,
        "ChatCompletionClient",
        lambda *args, **kwargs: FailingChat([f"```diff\n{patch}```"]),
    )
    with factory() as session:
        session.add(FixerRunRecord(id="partial", repo_full_name="owner/repo", issue_number=1))
        session.commit()
    assert runner.claim_next_run(factory, run_id="partial") == "partial"
    asyncio.run(runner.process_run("partial", settings=settings, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, "partial")
        bill = row.result_json["billing"]
        assert row.status == "failed"
        assert row.failure_category == "model_error"
        assert row.rounds == 2 and row.token_in == 10 and row.token_out == 5
        assert row.cost_usd is None
        assert bill["estimated_cost_usd"] is None
        assert bill["known_cost_subtotal_usd"] == 0.00002
        assert len(bill["calls"]) == 2
        assert bill["calls"][1]["status"] == "failed"
        latest = session.execute(
            select(FixerPatchRecord)
            .where(
                FixerPatchRecord.run_id == "partial",
            )
            .order_by(FixerPatchRecord.id.desc())
            .limit(1)
        ).scalar_one()
        assert "return bool(token)" in latest.diff
        evidence = row.result_json["evidence"]
    from pathlib import Path

    root = (
        Path(settings.agent_workspace_root)
        / "_evidence"
        / evidence["run_key"]
        / evidence["attempt_id"]
    )
    receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["stage"] == "failed"
    assert receipt["billing"]["estimated_cost_usd"] is None
    assert "return bool(token)" in (root / "patch.diff").read_text(encoding="utf-8")
    assert (root / "working.diff").exists()
    events = [
        json.loads(line)
        for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    calls = [event for event in events if event["event"] == "provider_call"]
    assert [call["status"] for call in calls] == ["started", "completed", "started", "failed"]


def test_no_provider_calls_is_known_zero_not_a_missing_price_estimate(pipeline, monkeypatch):
    factory, settings, execution = pipeline
    execution = copy.deepcopy(execution)
    artifact = execution["acceptance"]["files"][0]
    artifact["content"] = artifact["content"].replace(
        "self.assertIs(type(login_user('yes')), bool)",
        "self.assertTrue(login_user('yes'))",
    )
    artifact["sha256"] = hashlib.sha256(artifact["content"].encode()).hexdigest()
    with factory() as session:
        session.add(
            FixerRunRecord(
                id="no-calls",
                repo_full_name="owner/repo",
                issue_number=1,
                execution_spec={"spec": execution},
            )
        )
        session.commit()
    assert runner.claim_next_run(factory, run_id="no-calls") == "no-calls"
    asyncio.run(runner.process_run("no-calls", settings=settings, session_factory=factory))
    with factory() as session:
        row = session.get(FixerRunRecord, "no-calls")
        assert row.cost_usd == 0
        assert row.result_json["billing"]["call_count"] == 0
        assert row.result_json["billing"]["state"] == "known"
