"""Queue consumer for fixer runs.

Claims ``fixer_runs`` rows with ``FOR UPDATE SKIP LOCKED`` so several worker processes can
drain the same queue without double-executing, clones the target repository, runs locator +
fixer inside a sandbox, and records every step for the SSE timeline.
"""

import argparse
import asyncio
import shutil
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from packages.agent_core.fixer import FAILURE_TEST_ENVIRONMENT, FixerAgent, FixerConfig
from packages.agent_core.ingestion import clone_repository, workspace_root
from packages.agent_core.issue_parser import enrich_issue, parse_issue
from packages.agent_core.llm import ChatCompletionClient
from packages.agent_core.locator import locate
from packages.database.session import create_db_engine, create_session_factory
from packages.domain.models.fixer import FixerPatchRecord, FixerRunRecord, FixerStepRecord
from packages.domain.settings import Settings, get_settings
from packages.embeddings import OpenAIEmbeddingClient
from packages.github_client import GitHubClient
from packages.sandbox import create_sandbox

TERMINAL_STATUSES = {"succeeded", "failed"}


def claim_next_run(session_factory: sessionmaker) -> str | None:
    """Fail abandoned runs, then claim one queued run without retrying old side effects."""
    with session_factory() as session:
        with session.begin():
            now = datetime.now(UTC)
            expired = select(FixerRunRecord).where(
                FixerRunRecord.status == "running",
                FixerRunRecord.updated_at < now - timedelta(minutes=30),
            )
            if session.get_bind().dialect.name == "postgresql":
                expired = expired.with_for_update(skip_locked=True)
            for row in session.scalars(expired):
                row.status = "failed"
                row.success = False
                row.failure_category = FAILURE_TEST_ENVIRONMENT
                row.error = "Worker heartbeat expired after 30 minutes; run will not be retried"
                row.completed_at = now
                row.updated_at = now

            statement = (
                select(FixerRunRecord)
                .where(FixerRunRecord.status == "queued")
                .order_by(FixerRunRecord.created_at)
                .limit(1)
            )
            if session.get_bind().dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            row = session.execute(statement).scalar_one_or_none()
            if row is None:
                return None
            row.status = "running"
            row.started_at = now
            row.updated_at = now
            return row.id


def _issue_text(issue) -> str:  # noqa: ANN001 - GitHubIssue
    parts = [f"#{issue.number} {issue.title}"]
    if issue.body:
        parts.append(issue.body)
    return "\n\n".join(parts)


def _persist_step_factory(session_factory: sessionmaker, run_id: str):
    async def persist_step(step) -> None:  # noqa: ANN001 - FixerStepTrace
        with session_factory() as session:
            session.execute(
                update(FixerRunRecord)
                .where(FixerRunRecord.id == run_id, FixerRunRecord.status == "running")
                .values(updated_at=datetime.now(UTC))
            )
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
            session.commit()

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
    workspace = None
    try:
        if session_factory is None:
            settings = settings or get_settings()
            session_factory = create_session_factory(create_db_engine(settings.database_url))

        with session_factory() as session:
            run = session.get(FixerRunRecord, run_id)
            if run is None or run.status != "running":
                return
            settings = settings or get_settings()
            repo_full_name = run.repo_full_name
            issue_number = run.issue_number
            config = FixerConfig(
                model=run.model or settings.fixer_model or settings.openai_model,
                max_rounds=run.max_rounds,
                token_budget=run.token_budget,
                input_cost_per_million=settings.fixer_input_cost_per_million,
                output_cost_per_million=settings.fixer_output_cost_per_million,
            )

        owner, _, name = repo_full_name.partition("/")
        if not owner or not name:
            raise ValueError("invalid repo_full_name")
        if issue_number is None:
            raise ValueError("run has no issue number")

        workspace_slug = f"{repo_full_name.replace('/', '__')}-{run_id[:8]}"
        workspace = workspace_root(settings.agent_workspace_root) / workspace_slug
        async with GitHubClient(
            token=settings.github_token,
            base_url=settings.github_api_url,
        ) as github:
            issue = await github.get_issue(owner, name, issue_number)
        issue_text = _issue_text(issue)

        if settings.openai_api_key is None:
            raise RuntimeError("model provider is not configured (OPENAI_API_KEY missing)")
        chat = ChatCompletionClient(
            settings.openai_api_key.get_secret_value(),
            model=config.model,
            base_url=settings.openai_api_url,
            input_cost_per_million=settings.fixer_input_cost_per_million,
            output_cost_per_million=settings.fixer_output_cost_per_million,
        )

        embedding_client: OpenAIEmbeddingClient | None = None
        if settings.embedding_api_key is not None and settings.embedding_model:
            embedding_client = OpenAIEmbeddingClient(
                settings.embedding_api_key,
                model=settings.embedding_model,
                base_url=settings.embedding_api_url,
                cost_per_million=settings.embedding_cost_per_million,
            )

        clone_url = f"https://github.com/{repo_full_name}.git"
        clone_repository(clone_url, workspace)

        with session_factory() as session:
            analysis = parse_issue(issue.title, issue.body)
            if chat is not None:
                analysis = await enrich_issue(analysis, chat, body=issue.body)
            candidates = await locate(
                session,
                repo_full_name,
                issue_text,
                search_terms=analysis.search_terms,
                embedding_client=embedding_client,
                embedding_model=settings.embedding_model,
            )

        sandbox = create_sandbox(backend or settings.sandbox_backend, workspace)
        agent = FixerAgent(
            chat_client=chat,
            sandbox=sandbox,
            issue_text=issue_text,
            locator_candidates=candidates,
            config=config,
            on_step=_persist_step_factory(session_factory, run_id),
        )
        result = await agent.run()

        with session_factory() as session:
            with session.begin():
                row = session.get(FixerRunRecord, run_id, with_for_update=True)
                if row is None or row.status != "running":
                    return
                row.status = "succeeded" if result.success else "failed"
                row.success = result.success
                row.failure_category = result.failure_category
                row.summary = result.summary
                row.rounds = result.rounds
                row.token_in = result.token_in
                row.token_out = result.token_out
                row.cost_usd = result.cost_usd
                row.completed_at = datetime.now(UTC)
                row.result_json = {
                    "locator": [
                        {"path": item.path, "score": item.score, "channels": list(item.channels)}
                        for item in candidates
                    ],
                    "failure_categories": result.failure_category,
                }
                session.add(
                    FixerPatchRecord(
                        run_id=run_id,
                        round=result.rounds,
                        diff=result.diff or None,
                        apply_ok=bool(result.diff) or None,
                        test_ok=result.test_ok,
                    )
                )
    except Exception as exc:  # noqa: BLE001 - worker boundary: record and continue
        if session_factory is None:
            raise  # No database connection is available to persist this failure.
        _fail(session_factory, run_id, f"{type(exc).__name__}: {exc}")
    finally:
        if workspace is not None and not keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)


def _fail(session_factory: sessionmaker, run_id: str, message: str) -> None:
    with session_factory() as session:
        with session.begin():
            row = session.get(FixerRunRecord, run_id, with_for_update=True)
            if row is not None and row.status not in TERMINAL_STATUSES:
                row.status = "failed"
                row.success = False
                row.failure_category = FAILURE_TEST_ENVIRONMENT
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
