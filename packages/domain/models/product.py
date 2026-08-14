from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from packages.domain.models.base import Base, TimestampMixin, utc_now
from packages.domain.models.repository import BIGINT_PK


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(
        BIGINT_PK,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        index=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_sha: Mapped[str | None] = mapped_column(String(255))


class IndexSyncCursor(TimestampMixin, Base):
    __tablename__ = "index_sync_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    next_page: Mapped[int] = mapped_column(Integer, default=1)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class SearchSession(Base):
    __tablename__ = "search_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_github_query: Mapped[str] = mapped_column(Text)
    source_total_count: Mapped[int] = mapped_column(Integer, default=0)
    eligible_candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    ranking_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RecommendationRecord(Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("session_id", "rank"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("search_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    repository_full_name: Mapped[str] = mapped_column(String(255), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    score_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FeedbackRecord(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("search_sessions.id", ondelete="SET NULL"),
        index=True,
    )
    repository: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str | None] = mapped_column(String(240))
    query: Mapped[str | None] = mapped_column(String(500))
    device_id: Mapped[str | None] = mapped_column(String(64), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SavedRepository(TimestampMixin, Base):
    __tablename__ = "saved_repositories"
    __table_args__ = (UniqueConstraint("device_id", "repository"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    repository: Mapped[str] = mapped_column(String(255), index=True)


class ContributionIssueRecord(Base):
    __tablename__ = "contribution_issues"
    __table_args__ = (UniqueConstraint("repository_full_name", "issue_number"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    repository_full_name: Mapped[str] = mapped_column(String(255), index=True)
    issue_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    html_url: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(20), default="open")
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RepositoryDetailCache(TimestampMixin, Base):
    __tablename__ = "repository_detail_cache"

    repository_full_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    investigation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    investigation_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issues_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    issues_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    search_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("search_sessions.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentStepRecord(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        index=True,
    )
    node: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
