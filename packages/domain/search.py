from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)
    purpose: Literal["learning", "contribution"] | None = None
    weekly_hours: int | None = Field(default=None, ge=1, le=40)
    platform: str | None = Field(default=None, max_length=40)
    project_size: Literal["small", "medium", "large"] | None = None
    licenses: list[str] | None = None
    pushed_after: date | None = None


class SearchConstraints(BaseModel):
    purpose: Literal["learning", "contribution"] = "learning"
    language: str = "Python"
    technologies: list[str] = Field(default_factory=list)
    licenses: list[str] = Field(default_factory=list)
    exclude_archived: bool = True
    pushed_after: date | None = None
    weekly_hours: int | None = None
    platform: str | None = None
    project_size: Literal["small", "medium", "large"] | None = None


class Recommendation(BaseModel):
    rank: int
    full_name: str
    description: str | None
    html_url: str
    score: float
    stars: int
    language: str | None
    license_spdx: str | None
    pushed_at: datetime | None
    constraint_match: dict[str, Literal["MATCH", "MISMATCH", "UNKNOWN"]]
    score_breakdown: dict[str, float]
    reasons: list[str]
    risks: list[str]
    retrieval_sources: list[Literal["local_index", "github_live"]] = Field(
        default_factory=list
    )
    data_fetched_at: datetime | None = None


class RetrievalSummary(BaseModel):
    local_candidates: int = 0
    github_candidates: int = 0
    github_status: Literal["live", "unavailable"] = "live"
    index_freshest_at: datetime | None = None


class SearchResponse(BaseModel):
    session_id: str
    query: str
    generated_github_query: str
    constraints: SearchConstraints
    source_total_count: int
    eligible_candidate_count: int
    ranking_version: str
    results: list[Recommendation]
    retrieval: RetrievalSummary = Field(default_factory=RetrievalSummary)
