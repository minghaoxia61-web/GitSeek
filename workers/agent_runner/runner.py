"""Queue consumer for fixer runs.

Claims ``fixer_runs`` rows with ``FOR UPDATE SKIP LOCKED`` so several worker processes can
drain the same queue without double-executing, clones the target repository, runs locator +
fixer inside a sandbox, and records every step for the SSE timeline.
"""

import argparse
import asyncio
import shutil
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from packages.agent_core.acceptance import AcceptanceError, CleanAcceptance, acceptance_passed
from packages.agent_core.evidence import EvidenceArchive, source_identity
from packages.agent_core.execution import (
    ExecutionIdentityError,
    ExecutionSpec,
    canonical_sha256,
    verify_dependency_lock,
    verify_environment,
)
from packages.agent_core.fixer import FixerAgent, FixerConfig, FixerRunError
from packages.agent_core.ingestion import (
    IngestionError,
    clone_repository,
    ingest_repository,
    verify_checkout,
    workspace_root,
)
from packages.agent_core.issue_parser import enrich_issue, parse_issue
from packages.agent_core.llm import ChatCompletionClient
from packages.agent_core.locator import locate
from packages.database.session import create_db_engine, create_session_factory
from packages.domain.models.fixer import (
    AgentCodeChunkRecord,
    FixerPatchRecord,
    FixerRunRecord,
    FixerStepRecord,
)
from packages.domain.settings import Settings, get_settings
from packages.embeddings import OpenAIEmbeddingClient
from packages.github_client import GitHubClient
from packages.observability.calls import ReceiptPersistenceError, UsageLedger
from packages.sandbox import create_sandbox

TERMINAL_STATUSES = {"succeeded", "failed"}


def claim_next_run(session_factory: sessionmaker, *, run_id: str | None = None) -> str | None:
    """Claim one queued run; SKIP LOCKED keeps concurrent workers from colliding."""
    with session_factory() as session:
        with session.begin():
            statement = (
                select(FixerRunRecord)
                .where(FixerRunRecord.status == "queued")
                .order_by(FixerRunRecord.created_at)
                .limit(1)
            )
            if run_id is not None:
                statement = statement.where(FixerRunRecord.id == run_id)
            if session.get_bind().dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                return None
            row.status = "running"
            row.started_at = datetime.now(UTC)
            return row.id


def _issue_text(issue) -> str:  # noqa: ANN001 - GitHubIssue
    parts = [f"#{issue.number} {issue.title}"]
    if issue.body:
        parts.append(issue.body)
    return "\n\n".join(parts)


def _save_patch(session, run_id: str, round_no: int, diff: str, *, apply_ok=None, test_ok=None):
    patch = session.execute(
        select(FixerPatchRecord)
        .where(
            FixerPatchRecord.run_id == run_id,
            FixerPatchRecord.round == round_no,
        )
        .order_by(FixerPatchRecord.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if patch is None:
        patch = FixerPatchRecord(run_id=run_id, round=round_no)
        session.add(patch)
    patch.diff = diff or None
    patch.apply_ok = apply_ok
    patch.test_ok = test_ok


def _persist_step_factory(
    session_factory: sessionmaker, run_id: str, *, archive=None, workspace=None
):
    async def save_step(step) -> None:  # noqa: ANN001 - FixerStepTrace
        diff = None
        if archive:
            archive.event("tool_step", asdict(step))
            if workspace and step.tool in {"run_bash", "apply_patch"}:
                captured = subprocess.run(
                    ["git", "-C", str(workspace), "diff", "--no-ext-diff", "--binary", "HEAD"],
                    capture_output=True,
                    timeout=30,
                )
                if captured.returncode == 0:
                    diff = captured.stdout.decode("utf-8")
                    archive.patch(diff, name="working.diff")
        with session_factory() as session:
            session.add(
                FixerStepRecord(
                    run_id=run_id,
                    seq=step.seq,
                    round=step.round,
                    tool=step.tool,
                    input_json=step.input,
                    output=step.output,
                    latency_ms=step.latency_ms,
                )
            )
            if diff is not None:
                _save_patch(session, run_id, step.round, diff)
            row = session.get(FixerRunRecord, run_id)
            row.rounds = max(row.rounds, step.round)
            session.commit()

    async def persist_step(step):
        try:
            await save_step(step)
        except Exception as exc:
            raise ReceiptPersistenceError("cannot persist tool evidence") from exc

    return persist_step


async def process_run(
    run_id: str,
    *,
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
    backend: str | None = None,
    keep_workspace: bool = False,
) -> None:
    """Execute one claimed run end-to-end; any exception marks the run failed."""
    settings = settings or get_settings()
    if session_factory is None:
        session_factory = create_session_factory(create_db_engine(settings.database_url))

    with session_factory() as session:
        run = session.get(FixerRunRecord, run_id)
        if run is None:
            return
        repo_full_name = run.repo_full_name
        issue_number = run.issue_number
        model = run.model
        requested_execution = run.execution_spec
        config = FixerConfig(
            model=model or settings.fixer_model or settings.openai_model,
            max_rounds=run.max_rounds,
            token_budget=run.token_budget,
            test_command=run.test_command,
            input_cost_per_million=settings.fixer_input_cost_per_million,
            output_cost_per_million=settings.fixer_output_cost_per_million,
        )

    owner, _, name = repo_full_name.partition("/")
    if not owner or not name:
        _fail(session_factory, run_id, "invalid repo_full_name")
        return

    workspace_slug = f"{repo_full_name.replace('/', '__')}-{run_id[:8]}"
    workspace = workspace_root(settings.agent_workspace_root) / workspace_slug
    index_scope = None
    acceptance = None
    chat = None
    embedding_client = None
    result = None
    execution = {
        "requested": requested_execution,
        "identity_verified": False,
        "agent_source": source_identity(),
    }
    archive = EvidenceArchive(
        Path(settings.agent_evidence_root)
        if settings.agent_evidence_root
        else workspace_root(settings.agent_workspace_root) / "_evidence",
        run_id,
    )
    evidence = {
        "version": "run-evidence-v1",
        "run_key": archive.root.parent.name,
        "attempt_id": archive.root.name,
        "receipt": "receipt.json",
        "events": "events.jsonl",
    }
    last_stage = "started"
    last_error = None

    def receipt(stage: str, error: str | None = None):
        nonlocal last_stage, last_error
        last_stage, last_error = stage, error
        payload = {
            "version": "run-evidence-v1",
            "run_id": run_id,
            "stage": stage,
            "execution": execution,
            "billing": ledger.snapshot(),
            "error": error,
            "acceptance": acceptance.receipt if acceptance else None,
        }
        if result is not None:
            payload["verification"] = result.verification()
            payload["patch"] = archive.patch(result.diff)
            payload["success"] = result.success
            payload["rounds"] = result.rounds
            payload["failure_category"] = result.failure_category
        archive.receipt(payload)

    async def checkpoint_call(call):
        archive.event("provider_call", call)
        receipt("provider_call")
        billing = ledger.snapshot()
        with session_factory() as session:
            row = session.get(FixerRunRecord, run_id)
            row.result_json = {**(row.result_json or {}), "billing": billing, "evidence": evidence}
            row.token_in = billing["chat_input_tokens"]
            row.token_out = billing["chat_output_tokens"]
            row.cost_usd = billing["estimated_cost_usd"]
            session.commit()

    ledger = UsageLedger(on_change=checkpoint_call, token_budget=config.token_budget)
    receipt("started")
    try:
        if issue_number is None:
            raise ValueError("run has no issue number")
        spec = (
            ExecutionSpec.model_validate(requested_execution["spec"])
            if requested_execution is not None
            else None
        )
        selected_backend = backend or (
            spec.environment.backend if spec else settings.sandbox_backend
        )
        with session_factory() as session:
            row = session.get(FixerRunRecord, run_id)
            row.result_json = {**(row.result_json or {}), "execution": execution}
            session.commit()
        if spec and selected_backend != spec.environment.backend:
            raise ExecutionIdentityError("backend override does not match execution spec")
        clone_url = f"https://github.com/{repo_full_name}.git"
        clone_repository(clone_url, workspace, base_commit=spec.base_commit if spec else None)
        execution["actual_commit"] = verify_checkout(workspace, spec.base_commit if spec else None)
        if spec:
            execution["dependency_lock"] = verify_dependency_lock(workspace, spec.dependency_lock)
            execution["environment"] = verify_environment(spec.environment)
            execution["identity_verified"] = True
        execution["model_config"] = asdict(config)
        execution["model_config_sha256"] = canonical_sha256(asdict(config))
        with session_factory() as session:
            row = session.get(FixerRunRecord, run_id)
            row.result_json = {**(row.result_json or {}), "execution": execution}
            session.commit()

        if spec and spec.acceptance is not None:
            acceptance = CleanAcceptance(workspace, spec, sandbox_factory=create_sandbox)
            await acceptance.prepare()
            with session_factory() as session:
                row = session.get(FixerRunRecord, run_id)
                row.result_json = {**(row.result_json or {}), "acceptance": acceptance.receipt}
                session.commit()

        async with GitHubClient(
            token=settings.github_token,
            base_url=settings.github_api_url,
        ) as github:
            issue = await github.get_issue(owner, name, issue_number)
        issue_text = _issue_text(issue)
        execution["issue_snapshot"] = {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
        }
        execution["issue_sha256"] = canonical_sha256(execution["issue_snapshot"])
        receipt("issue_loaded")

        if settings.openai_api_key is None:
            raise RuntimeError("model provider is not configured (OPENAI_API_KEY missing)")
        chat = ledger.observe(
            ChatCompletionClient(
                settings.openai_api_key.get_secret_value(),
                model=config.model,
                base_url=settings.openai_api_url,
                input_cost_per_million=settings.fixer_input_cost_per_million,
                output_cost_per_million=settings.fixer_output_cost_per_million,
            ),
            kind="chat",
            input_rate=settings.fixer_input_cost_per_million,
            output_rate=settings.fixer_output_cost_per_million,
            phase="issue_enrichment",
        )

        embedding_client: OpenAIEmbeddingClient | None = None
        if settings.embedding_api_key is not None and settings.embedding_model:
            embedding_rate = settings.fixer_embedding_cost_per_million
            if embedding_rate is None and settings.embedding_cost_per_million > 0:
                embedding_rate = settings.embedding_cost_per_million
            embedding_client = ledger.observe(
                OpenAIEmbeddingClient(
                    settings.embedding_api_key,
                    model=settings.embedding_model,
                    base_url=settings.embedding_api_url,
                    cost_per_million=embedding_rate,
                ),
                kind="embedding",
                input_rate=embedding_rate,
                output_rate=0,
                phase="code_retrieval",
            )

        with session_factory() as session:
            if spec:
                # Never query a default-branch index when repairing a historical revision.
                index_scope = f"fixer-run:{run_id}"
                await ingest_repository(
                    session,
                    index_scope,
                    workspace,
                    embedding_client=embedding_client,
                    embedding_model=settings.embedding_model,
                )
                execution["index_source_commit"] = execution["actual_commit"]
            analysis = parse_issue(issue.title, issue.body)
            if chat is not None:
                analysis = await enrich_issue(analysis, chat, body=issue.body)
            candidates = await locate(
                session,
                index_scope or repo_full_name,
                issue_text,
                search_terms=analysis.search_terms,
                embedding_client=embedding_client,
                embedding_model=settings.embedding_model,
            )

        sandbox_options = (
            {"image": spec.environment.image, "platform": spec.environment.platform}
            if spec and selected_backend == "docker"
            else {}
        )
        sandbox = create_sandbox(selected_backend, workspace, **sandbox_options)
        chat.phase = "repair"
        agent = FixerAgent(
            chat_client=chat,
            sandbox=sandbox,
            issue_text=issue_text,
            locator_candidates=candidates,
            config=config,
            on_step=_persist_step_factory(
                session_factory, run_id, archive=archive, workspace=workspace
            ),
        )
        result = await agent.run()
        execution["final_commit"] = verify_checkout(
            workspace,
            execution["actual_commit"],
            require_clean=False,
        )
        acceptance_error = None
        if acceptance:
            try:
                await acceptance.verify(result.diff)
            except AcceptanceError as exc:
                result.success = False
                result.failure_category = exc.category
                acceptance_error = str(exc)
            if not acceptance_passed(acceptance.receipt):
                result.success = False

        receipt("completed", acceptance_error)
        billing = ledger.snapshot()
        with session_factory() as session:
            with session.begin():
                row = session.get(FixerRunRecord, run_id)
                row.status = "succeeded" if result.success else "failed"
                row.success = result.success
                row.failure_category = result.failure_category
                row.summary = result.summary
                row.error = acceptance_error
                row.rounds = result.rounds
                row.token_in = billing["chat_input_tokens"]
                row.token_out = billing["chat_output_tokens"]
                row.cost_usd = billing["estimated_cost_usd"]
                row.completed_at = datetime.now(UTC)
                row.result_json = {
                    **(row.result_json or {}),
                    "execution": execution,
                    "locator": [
                        {"path": item.path, "score": item.score, "channels": list(item.channels)}
                        for item in candidates
                    ],
                    "failure_categories": result.failure_category,
                    "verification": result.verification(),
                    "acceptance": acceptance.receipt if acceptance else None,
                    "billing": billing,
                    "evidence": evidence,
                }
                _save_patch(
                    session,
                    run_id,
                    result.rounds,
                    result.diff,
                    apply_ok=result.apply_ok,
                    test_ok=result.test_ok,
                )
    except asyncio.CancelledError:
        receipt("cancelled", "asyncio.CancelledError")
        _fail(session_factory, run_id, "run was cancelled", category="cancelled")
        raise
    except Exception as exc:  # noqa: BLE001 - worker boundary: record and continue
        if isinstance(exc, FixerRunError):
            result = exc.result
        category = (
            result.failure_category
            if isinstance(exc, FixerRunError)
            else exc.category
            if isinstance(exc, AcceptanceError)
            else "execution_identity_error"
            if isinstance(exc, (ExecutionIdentityError, IngestionError, ValidationError))
            else "execution_error"
        )
        if result is not None:
            result.success = False
            result.failure_category = category
        receipt("failed", f"{type(exc).__name__}: {exc}")
        billing = ledger.snapshot()
        with session_factory() as session:
            row = session.get(FixerRunRecord, run_id)
            row.result_json = {
                **(row.result_json or {}),
                "execution": execution,
                "acceptance": acceptance.receipt if acceptance else None,
                "billing": billing,
                "evidence": evidence,
            }
            row.token_in = billing["chat_input_tokens"]
            row.token_out = billing["chat_output_tokens"]
            row.cost_usd = billing["estimated_cost_usd"]
            if result is not None:
                row.rounds = result.rounds
                row.result_json = {**row.result_json, "verification": result.verification()}
                _save_patch(
                    session,
                    run_id,
                    result.rounds,
                    result.diff,
                    apply_ok=result.apply_ok,
                    test_ok=result.test_ok,
                )
            session.commit()
        _fail(session_factory, run_id, f"{type(exc).__name__}: {exc}", category=category)
    finally:
        cleanup_warnings = []
        for client in (chat, embedding_client):
            if client is not None:
                try:
                    await client.aclose()
                except Exception as exc:
                    archive.event("client_cleanup_error", {"error_type": type(exc).__name__})
                    cleanup_warnings.append(f"client:{type(exc).__name__}")
        if acceptance and not keep_workspace:
            try:
                acceptance.cleanup()
            except Exception as exc:
                cleanup_warnings.append(f"acceptance:{type(exc).__name__}")
        if index_scope:
            try:
                with session_factory() as session:
                    session.execute(
                        delete(AgentCodeChunkRecord).where(
                            AgentCodeChunkRecord.repo_full_name == index_scope,
                        )
                    )
                    session.commit()
            except Exception as exc:
                cleanup_warnings.append(f"index:{type(exc).__name__}")
        if not keep_workspace:
            if (
                workspace.resolve().parent
                == workspace_root(settings.agent_workspace_root).resolve()
                and not workspace.is_symlink()
            ):
                shutil.rmtree(workspace, ignore_errors=True)
                if workspace.exists():
                    cleanup_warnings.append("workspace:partially_retained")
            else:
                cleanup_warnings.append("workspace:unsafe_cleanup_target")
        execution["cleanup_warnings"] = cleanup_warnings
        archive.event("cleanup", {"warnings": cleanup_warnings, "kept_workspace": keep_workspace})
        receipt(last_stage, last_error)


def _fail(
    session_factory: sessionmaker, run_id: str, message: str, *, category: str = "execution_error"
) -> None:
    with session_factory() as session:
        with session.begin():
            row = session.get(FixerRunRecord, run_id)
            if row is not None and row.status not in TERMINAL_STATUSES:
                row.status = "failed"
                row.success = False
                row.failure_category = category
                row.error = message[:1000]
                row.completed_at = datetime.now(UTC)


async def _loop(
    *,
    once: bool,
    poll_seconds: float,
    backend: str | None,
    keep_workspace: bool,
) -> None:
    settings = get_settings()
    session_factory = create_session_factory(create_db_engine(settings.database_url))
    while True:
        run_id = claim_next_run(session_factory)
        if run_id is None:
            if once:
                return
            time.sleep(poll_seconds)
            continue
        await process_run(
            run_id,
            settings=settings,
            session_factory=session_factory,
            backend=backend,
            keep_workspace=keep_workspace,
        )
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="GitSeek fixer-agent queue runner")
    parser.add_argument("--once", action="store_true", help="process at most one run and exit")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--backend", choices=["local", "docker"], default=None)
    parser.add_argument("--keep-workspaces", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        _loop(
            once=args.once,
            poll_seconds=args.poll_seconds,
            backend=args.backend,
            keep_workspace=args.keep_workspaces,
        )
    )


if __name__ == "__main__":
    main()
