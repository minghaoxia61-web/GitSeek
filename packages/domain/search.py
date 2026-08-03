from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)


class SearchConstraints(BaseModel):
    language: str = "Python"
    technologies: list[str] = Field(default_factory=list)
    licenses: list[str] = Field(default_factory=list)
    exclude_archived: bool = True
    pushed_after: date | None = None


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


class SearchResponse(BaseModel):
    query: str
    generated_github_query: str
    constraints: SearchConstraints
    source_total_count: int
    eligible_candidate_count: int
    ranking_version: str
    results: list[Recommendation]

