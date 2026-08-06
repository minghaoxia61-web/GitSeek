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
