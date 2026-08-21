from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ContributionIssue(BaseModel):
    number: int
    title: str
    html_url: str
    labels: list[str] = Field(default_factory=list)
    comments: int = 0
    updated_at: datetime
    difficulty: Literal["easy", "medium", "hard"]
    score: float = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ContributionIssueResponse(BaseModel):
    full_name: str
    fetched_at: datetime
    issues: list[ContributionIssue]
    limitations: list[str] = Field(default_factory=list)


class DeveloperProfile(BaseModel):
    username: str
    name: str | None = None
    html_url: str
    experience_level: Literal["beginner", "intermediate", "advanced"]
    public_repository_count: int = 0
    sampled_repository_count: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    technologies: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ContributionIssueMatch(ContributionIssue):
    fit_score: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    start_checklist: list[str] = Field(default_factory=list)


class ContributionIssueMatchResponse(BaseModel):
    full_name: str
    profile: DeveloperProfile
    fetched_at: datetime
    issues: list[ContributionIssueMatch]
    limitations: list[str] = Field(default_factory=list)
