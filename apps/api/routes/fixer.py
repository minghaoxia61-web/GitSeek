"""HTTP surface for the issue-to-PR fixer agent.

The queue lives in ``fixer_runs`` and is drained by ``workers.agent_runner`` (a separate
process), so the SSE stream tails the database instead of an in-memory queue.
"""

import asyncio
import json
import re
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session
from packages.domain.models.fixer import (
    FIXER_RUN_STATUSES,
    FixerPatchRecord,
    FixerRunRecord,
    FixerStepRecord,
)

router = APIRouter(prefix="/api/v1/fixer", tags=["fixer agent"])

STREAM_POLL_SECONDS = 1.0
STREAM_KEEPALIVE_EVERY = 15
STREAM_MAX_SECONDS = 900.0

ISSUE_URL_RE = re.compile(r"/issues/(\d+)")
REPO_NAME_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class FixerRunCreate(BaseModel):
    repo_full_name: str = Field(min_length=3, max_length=255)
    issue_url: str | None = Field(default=None, max_length=500)
    issue_number: int | None = Field(default=None, ge=1)
    model: str | None = Field(default=None, max_length=160)
    max_rounds: int | None = Field(default=None, ge=1, le=10)
    token_budget: int | None = Field(default=None, ge=10_000, le=2_000_000)

    @model_validator(mode="after")
    def resolve_issue_number(self) -> "FixerRunCreate":
        if not REPO_NAME_RE.match(self.repo_full_name):
            raise ValueError("repo_full_name must look like owner/repo")
        if self.issue_number is None and self.issue_url:
            match = ISSUE_URL_RE.search(self.issue_url)
            if not match:
                raise ValueError("issue_url must contain /issues/<number>")
            self.issue_number = int(match.group(1))
        if self.issue_number is None:
            raise ValueError("provide issue_number or issue_url")
        return self


def _run_payload(session: Session, run: FixerRunRecord, *, include_diff: bool = False) -> dict:
    step_count = session.execute(
        select(func.count()).select_from(FixerStepRecord).where(FixerStepRecord.run_id == run.id)
    ).scalar_one()
    payload = {
        "run_id": run.id,
        "repo_full_name": run.repo_full_name,
        "issue_url": run.issue_url,
        "issue_number": run.issue_number,
        "status": run.status,
        "model": run.model,
        "max_rounds": run.max_rounds,
        "token_budget": run.token_budget,
        "rounds": run.rounds,
        "token_in": run.token_in,
        "token_out": run.token_out,
        "cost_usd": run.cost_usd,
        "success": run.success,
        "failure_category": run.failure_category,
        "summary": run.summary,
        "error": run.error,
        "step_count": step_count,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if include_diff:
        latest = session.execute(
            select(FixerPatchRecord)
            .where(FixerPatchRecord.run_id == run.id)
            .order_by(FixerPatchRecord.created_at.desc(), FixerPatchRecord.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        payload["diff"] = latest.diff if latest else None
    return payload


@router.post("/runs")
def create_run(body: FixerRunCreate, session: Annotated[Session, Depends(get_db_session)]) -> dict:
    from packages.domain.settings import get_settings

    settings = get_settings()
    run = FixerRunRecord(
        id=str(uuid4()),
        repo_full_name=body.repo_full_name,
        issue_url=body.issue_url,
        issue_number=body.issue_number,
        status="queued",
        model=body.model or settings.fixer_model or settings.openai_model,
        max_rounds=body.max_rounds or settings.fixer_max_rounds,
        token_budget=body.token_budget or settings.fixer_token_budget,
    )
    session.add(run)
    session.commit()
    return _run_payload(session, run)


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Annotated[Session, Depends(get_db_session)]) -> dict:
    run = session.get(FixerRunRecord, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="fixer run not found")
    return _run_payload(session, run)


@router.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str, session: Annotated[Session, Depends(get_db_session)]) -> dict:
    run = session.get(FixerRunRecord, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="fixer run not found")
    latest = session.execute(
        select(FixerPatchRecord)
        .where(FixerPatchRecord.run_id == run_id)
        .order_by(FixerPatchRecord.created_at.desc(), FixerPatchRecord.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {"run_id": run_id, "diff": latest.diff if latest else None}


def _get_factory():  # noqa: ANN201 - indirection so tests can inject an in-memory factory
    from packages.database.session import get_session_factory

    return get_session_factory()


def _snapshot(run_id: str, last_seq: int) -> dict | None:
    with _get_factory()() as session:
        run = session.get(FixerRunRecord, run_id)
        if run is None:
            return {"missing": True}
        steps = session.execute(
            select(FixerStepRecord)
            .where(FixerStepRecord.run_id == run_id)
            .where(FixerStepRecord.seq > last_seq)
            .order_by(FixerStepRecord.seq)
        ).scalars().all()
        return {
            "run": _run_payload(session, run, include_diff=run.status in {"succeeded", "failed"}),
            "steps": [
                {
                    "seq": step.seq,
                    "round": step.round,
                    "tool": step.tool,
                    "input": step.input_json,
                    "output": step.output,
                    "latency_ms": step.latency_ms,
                }
                for step in steps
            ],
        }


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    async def events():
        last_seq = 0
        polls = 0
        deadline = time.monotonic() + STREAM_MAX_SECONDS
        yield f"event: open\ndata: {json.dumps({'run_id': run_id})}\n\n"
        while True:
            snapshot = await asyncio.to_thread(_snapshot, run_id, last_seq)
            if snapshot is None or snapshot.get("missing"):
                yield f"event: error\ndata: {json.dumps({'message': 'fixer run not found'})}\n\n"
                return
            for step in snapshot["steps"]:
                last_seq = step["seq"]
                yield f"event: step\ndata: {json.dumps(step, ensure_ascii=False)}\n\n"
            run_status = snapshot["run"]["status"]
            if run_status in {"succeeded", "failed"}:
                yield f"event: result\ndata: {json.dumps(snapshot['run'], ensure_ascii=False)}\n\n"
                return
            if time.monotonic() > deadline:
                timeout_payload = json.dumps({"message": "stream timed out waiting for the run"})
                yield f"event: error\ndata: {timeout_payload}\n\n"
                return
            polls += 1
            if polls % STREAM_KEEPALIVE_EVERY == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router", "FIXER_RUN_STATUSES"]
