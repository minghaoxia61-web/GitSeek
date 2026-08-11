from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    id: str
    fact: str
    value: bool | int | float | str
    source_url: str
    fetched_at: datetime
    confidence: Literal["high", "medium", "low"]


class EngineeringSignals(BaseModel):
    has_readme: bool
    has_contributing: bool
    has_code_of_conduct: bool
    has_issue_template: bool
    has_pull_request_template: bool
    has_security_policy: bool
    has_license: bool
    has_tests: bool
    has_ci: bool
    has_pyproject: bool
    has_dependency_file: bool
    has_docker: bool
    readme_has_quickstart: bool


class InvestigationScores(BaseModel):
    community_health: float = Field(ge=0, le=100)
    documentation: float = Field(ge=0, le=100)
    engineering: float = Field(ge=0, le=100)
    learning_friendliness: float = Field(ge=0, le=100)
    maintenance: float = Field(ge=0, le=100)


class ActivitySignals(BaseModel):
    releases_sampled: int = 0
    latest_release_at: datetime | None = None
    median_release_interval_days: float | None = None
    pull_requests_sampled: int = 0
    merged_pull_request_ratio: float | None = None
    median_pull_request_resolution_hours: float | None = None
    contributors_sampled: int = 0
    top_contributor_share: float | None = None
    contributor_continuity: Literal["distributed", "concentrated", "unknown"] = "unknown"


class RepositoryInvestigation(BaseModel):
    full_name: str
    description: str | None
    html_url: str
    default_branch: str
    fetched_at: datetime
    confidence: Literal["high", "medium", "low"]
    signals: EngineeringSignals
    activity: ActivitySignals
    scores: InvestigationScores
    evidence: list[EvidenceItem]
    risks: list[str]
    limitations: list[str]
