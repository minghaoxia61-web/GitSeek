import asyncio
import json
import os
import shlex
import subprocess
from pathlib import Path
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from apps.api.dependencies import get_db_session
from apps.api.main import app
from packages.agent_core.fixer import FixerConfig
from packages.agent_core.ingestion import clone_repository, ingest_repository
from packages.agent_core.llm import ChatCompletionClient
from packages.domain.models import Base
from packages.domain.models.fixer import FixerPatchRecord, FixerRunRecord
from packages.domain.settings import Settings
from packages.sandbox import DockerSandbox
from workers.agent_runner import runner

REPO = "mahmoud/boltons"
ISSUE_URL = "https://github.com/mahmoud/boltons/issues/348"
BASE_COMMIT = "46599bc0d498dd8adc3aea833ce1445feed349dd"
REFERENCE_COMMIT = "4815fc8dd1768da5f2d903846d2ab994aa57b0cf"
IMAGE = "gitseek-issue-check:local"
REGRESSION = """from boltons.cacheutils import LRU, LRI
for cache_type in (LRU, LRI):
    for size in (1, 3, 128):
        cache = cache_type(max_size=size)
        for value in (1, 200, -3, None):
            cache['a'] = value
            assert cache['a'] == value
            assert dict(cache) == {'a': value}, 'replacement is stale'
            assert list(cache.values()) == [value]
            assert list(cache.items()) == [('a', value)]
            assert len(cache) == 1
print('24 cache replacement cases passed')
"""
TEST_COMMAND = (
    "python -m pytest tests/test_cacheutils.py -q && python -c " + shlex.quote(REGRESSION)
)


def git(workspace, *args):
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=True, capture_output=True, text=True, timeout=120,
    ).stdout.strip()


def fetch_revision(workspace, revision):
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "fetch", "--depth=1", f"https://github.com/{REPO}.git", revision)
    git(workspace, "checkout", "--detach", "FETCH_HEAD")
    assert git(workspace, "rev-parse", "HEAD") == revision


@pytest.mark.skipif(
    os.environ.get("OPENSCOUT_RUN_REAL_ISSUE") != "1",
    reason="real model acceptance requires explicit opt-in",
)
def test_real_issue_through_api_worker_and_saved_patch(tmp_path, monkeypatch):
    started = monotonic()
    output = Path(os.environ.get("OPENSCOUT_ACCEPTANCE_OUTPUT", str(tmp_path / "report")))
    output.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'acceptance.sqlite'}"
    settings = Settings(_env_file=None).model_copy(update={
        "database_url": database_url,
        "agent_workspace_root": str(tmp_path / "workspaces"),
        "sandbox_backend": "docker",
        "embedding_api_key": None,
        "embedding_model": None,
    })
    assert settings.openai_api_key is not None
    assert settings.openai_api_url == "https://api.deepseek.com"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    report = {
        "issue_url": ISSUE_URL,
        "base_commit": BASE_COMMIT,
        "reference_commit": REFERENCE_COMMIT,
        "database": "temporary SQLite; production queue untouched",
        "source_adapter": "pinned public GitHub snapshot cloned through the real clone helper",
        "test_adapter": "trusted command and prebuilt pytest image",
        "max_rounds": 6,
        "token_budget": 100_000,
        "cost_reporting": "token counts include enrichment; cost_usd depends on configured rates",
        "accepted": False,
        "model_calls": [],
        "checks": {},
    }
    seed = tmp_path / "base"
    reference = tmp_path / "reference"
    patch_text = ""
    timeline = {}

    class RecordingChat(ChatCompletionClient):
        async def complete(self, messages, **kwargs):
            phase = "repair" if messages[0]["role"] == "system" else "issue_enrichment"
            calls = report["model_calls"]
            spent = sum(call["input_tokens"] + call["output_tokens"] for call in calls)
            # UTF-8 bytes plus framing conservatively bound the next prompt's tokens.
            prompt_bound = sum(len(message["content"].encode("utf-8")) + 256
                               for message in messages)
            if phase == "repair":
                assert sum(call["phase"] == "repair" for call in calls) < 6
            assert spent + prompt_bound + kwargs.get("max_tokens", 4096) <= 100_000
            result = await super().complete(messages, **kwargs)
            report["model_calls"].append({
                "phase": phase,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            })
            return result

    def pinned_clone(clone_url, destination):
        assert clone_url == f"https://github.com/{REPO}.git"
        # A shallow local transport exposes only the broken revision, not the known fix.
        clone_repository(seed.as_uri(), destination)
        assert git(destination, "rev-parse", "HEAD") == BASE_COMMIT
        assert git(destination, "rev-list", "--count", "--all") == "1"
        return destination

    def sandbox_factory(backend, workspace):
        assert backend == "docker"
        return DockerSandbox(workspace, image=IMAGE)

    def override_db():
        with factory() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_db_session, override_db)
    monkeypatch.setattr("apps.api.routes.fixer._get_factory", lambda: factory)
    monkeypatch.setattr("packages.domain.settings.get_settings", lambda: settings)
    monkeypatch.setattr(runner, "clone_repository", pinned_clone)
    monkeypatch.setattr(runner, "create_sandbox", sandbox_factory)
    monkeypatch.setattr(runner, "ChatCompletionClient", RecordingChat)
    monkeypatch.setattr(
        runner, "FixerConfig", lambda **kwargs: FixerConfig(test_command=TEST_COMMAND, **kwargs),
    )

    async def check_workspace(label, workspace):
        result = await DockerSandbox(workspace, image=IMAGE).exec(TEST_COMMAND, timeout_s=180)
        report["checks"][label] = {
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stdout": result.stdout[-6000:],
            "stderr": result.stderr[-3000:],
        }
        return result

    try:
        fetch_revision(seed, BASE_COMMIT)
        baseline = asyncio.run(check_workspace("broken_baseline", seed))
        assert baseline.exit_code == 1 and not baseline.timed_out
        assert "replacement is stale" in baseline.stderr
        fetch_revision(reference, REFERENCE_COMMIT)
        known_fix = asyncio.run(check_workspace("maintainer_reference", reference))
        assert known_fix.exit_code == 0 and not known_fix.timed_out
        with factory() as session:
            stats = asyncio.run(ingest_repository(session, REPO, seed))
            assert stats.chunk_count > 0
            report["indexed_chunks"] = stats.chunk_count

        with TestClient(app) as client:
            created = client.post("/api/v1/fixer/runs", json={
                "repo_full_name": REPO,
                "issue_url": ISSUE_URL,
                "model": settings.openai_model,
                "max_rounds": 6,
                "token_budget": 100_000,
            })
            assert created.status_code == 200
            run_id = created.json()["run_id"]
            report["run_id"] = run_id
            assert created.json()["status"] == "queued"
            assert runner.claim_next_run(factory) == run_id
            assert client.get(f"/api/v1/fixer/runs/{run_id}").json()["status"] == "running"
            asyncio.run(runner.process_run(
                run_id, settings=settings, session_factory=factory,
                backend="docker", keep_workspace=True,
            ))
            run = client.get(f"/api/v1/fixer/runs/{run_id}").json()
            report["run"] = run
            timeline = client.get(f"/api/v1/fixer/runs/{run_id}/timeline").json()
            patch_text = client.get(f"/api/v1/fixer/runs/{run_id}/diff").json()["diff"] or ""
            assert run["status"] == "succeeded" and run["success"] is True, run
            assert run["failure_category"] is None
            assert run["token_in"] > 0 and run["token_out"] > 0
            assert 1 <= run["rounds"] <= 6
            assert run["token_in"] + run["token_out"] <= 100_000
            assert patch_text.strip() and timeline["run"]["diff"] == patch_text
            steps = timeline["steps"]
            assert len(steps) == run["step_count"]
            assert [step["seq"] for step in steps] == list(range(1, len(steps) + 1))
            assert any(step["tool"] == "run_tests" for step in steps)
            assert steps[-1]["tool"] == "finish"
            incremental = client.get(
                f"/api/v1/fixer/runs/{run_id}/timeline", params={"after_seq": steps[-1]["seq"]},
            ).json()
            assert incremental["steps"] == []
            assert incremental["run"]["status"] == "succeeded"
            stream = client.get(f"/api/v1/fixer/runs/{run_id}/stream")
            assert stream.status_code == 200 and "event: result" in stream.text
            with factory() as session:
                stored = session.scalar(select(FixerPatchRecord).where(
                    FixerPatchRecord.run_id == run_id,
                ))
                assert stored.test_ok is True and stored.diff == patch_text
                locations = session.get(FixerRunRecord, run_id).result_json["locator"]
                assert locations
                report["locator"] = locations

        replay = tmp_path / "replay"
        clone_repository(seed.as_uri(), replay)
        replay_sandbox = DockerSandbox(replay, image=IMAGE)
        applied = asyncio.run(replay_sandbox.exec(
            "git apply --index --whitespace=nowarn -", stdin=patch_text, timeout_s=30,
        ))
        assert applied.exit_code == 0, applied.stderr
        changed = git(replay, "diff", "--name-only", "HEAD").splitlines()
        report["changed_files"] = changed
        assert "boltons/cacheutils.py" in changed
        assert all(path.startswith("boltons/") for path in changed)
        replayed = asyncio.run(check_workspace("independent_patch_replay", replay))
        assert replayed.exit_code == 0 and not replayed.timed_out
        verified_diff = asyncio.run(replay_sandbox.exec("git diff --binary HEAD"))
        assert verified_diff.exit_code == 0 and verified_diff.stdout == patch_text
        assert len(report["model_calls"]) >= run["rounds"]
        assert sum(call["input_tokens"] + call["output_tokens"]
                   for call in report["model_calls"]) <= 100_000
        report["accepted"] = True
    finally:
        report["duration_s"] = round(monotonic() - started, 2)
        for name, content in (
            ("report.json", json.dumps(report, ensure_ascii=False, indent=2)),
            ("timeline.json", json.dumps(timeline, ensure_ascii=False, indent=2)),
            ("repair.diff", patch_text),
        ):
            for secret in (settings.openai_api_key, settings.github_token):
                if secret and secret.get_secret_value():
                    content = content.replace(secret.get_secret_value(), "[REDACTED]")
            (output / name).write_text(content, encoding="utf-8")
        engine.dispose()
        print(json.dumps({
            "issue": ISSUE_URL, "accepted": report["accepted"],
            "run_id": report.get("run_id"), "model_calls": report["model_calls"],
        }))
