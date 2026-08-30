"""Persistence models for the issue-to-PR fixer agent.

Table names are prefixed with ``fixer_`` because ``agent_runs`` / ``agent_steps``
already belong to the contribution-screening agent workflow.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from packages.domain.models.base import Base, TimestampMixin, utc_now
from packages.domain.models.repository import BIGINT_PK

FIXER_RUN_STATUSES = ("queued", "running", "succeeded", "failed")


class FixerRunRecord(TimestampMixin, Base):
    __tablename__ = "fixer_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), index=True)
    issue_url: Mapped[str | None] = mapped_column(String(500))
    issue_number: Mapped[int | None] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    model: Mapped[str | None] = mapped_column(String(160))
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)
    token_budget: Mapped[int] = mapped_column(Integer, default=200_000)
    rounds: Mapped[int] = mapped_column(Integer, default=0)
    token_in: Mapped[int] = mapped_column(Integer, default=0)
    token_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool | None] = mapped_column(Boolean)
    failure_category: Mapped[str | None] = mapped_column(String(60))
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FixerStepRecord(Base):
    __tablename__ = "fixer_steps"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fixer_runs.id", ondelete="CASCADE"),
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, index=True)
    round: Mapped[int] = mapped_column(Integer, default=0)
    tool: Mapped[str] = mapped_column(String(40))
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FixerPatchRecord(Base):
    __tablename__ = "fixer_patches"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fixer_runs.id", ondelete="CASCADE"),
        index=True,
    )
    round: Mapped[int] = mapped_column(Integer, default=0)
    diff: Mapped[str | None] = mapped_column(Text)
    apply_ok: Mapped[bool | None] = mapped_column(Boolean)
    test_ok: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentCodeChunkRecord(TimestampMixin, Base):
    __tablename__ = "agent_code_chunks"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), index=True)
    path: Mapped[str] = mapped_column(String(400))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    start_line: Mapped[int] = mapped_column(Integer, default=0)
    end_line: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(160), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    vector_json: Mapped[list[float] | None] = mapped_column(JSON)


class AgentBenchResultRecord(Base):
    __tablename__ = "agent_bench_results"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    config_id: Mapped[str] = mapped_column(String(120), index=True)
    dataset: Mapped[str] = mapped_column(String(120))
    instance_id: Mapped[str] = mapped_column(String(160), index=True)
    metric: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
