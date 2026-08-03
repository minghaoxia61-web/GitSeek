from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.domain.models.base import Base, TimestampMixin, utc_now

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    primary_language: Mapped[str | None] = mapped_column(String(100), index=True)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    license_spdx: Mapped[str | None] = mapped_column(String(100), index=True)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    github_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    github_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source_etag: Mapped[str | None] = mapped_column(String(255))
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    features: Mapped["RepositoryFeature | None"] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        uselist=False,
    )


class RepositoryFeature(TimestampMixin, Base):
    __tablename__ = "repository_features"

    repo_id: Mapped[int] = mapped_column(
        BIGINT_PK,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    has_readme: Mapped[bool | None] = mapped_column(Boolean)
    has_contributing: Mapped[bool | None] = mapped_column(Boolean)
    has_tests: Mapped[bool | None] = mapped_column(Boolean)
    has_ci: Mapped[bool | None] = mapped_column(Boolean)
    has_pyproject: Mapped[bool | None] = mapped_column(Boolean)
    recently_active: Mapped[bool | None] = mapped_column(Boolean)
    activity_score: Mapped[float | None] = mapped_column(Float)
    documentation_score: Mapped[float | None] = mapped_column(Float)
    learning_friendliness_score: Mapped[float | None] = mapped_column(Float)
    feature_version: Mapped[str] = mapped_column(String(50), default="v1")

    repository: Mapped[Repository] = relationship(back_populates="features")
