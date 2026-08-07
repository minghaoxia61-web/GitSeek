from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from packages.domain.search import SearchConstraints


class ModelQueryPlan(BaseModel):
    summary: str = Field(min_length=1, max_length=160)
    language: str = Field(min_length=1, max_length=40)
    technologies: list[str] = Field(default_factory=list, max_length=8)
    github_terms: list[str] = Field(default_factory=list, max_length=5)
    licenses: list[str] = Field(default_factory=list, max_length=5)
    purpose: Literal["learning", "contribution"] = "learning"
    exclude_archived: bool = True
    pushed_after: date | None = None
    weekly_hours: int | None = Field(default=None, ge=1, le=40)
    platform: str | None = Field(default=None, max_length=40)
    project_size: Literal["small", "medium", "large"] | None = None

    def constraints(self) -> SearchConstraints:
        return SearchConstraints(
            purpose=self.purpose,
            language=self.language,
            technologies=self.technologies,
            licenses=self.licenses,
            exclude_archived=self.exclude_archived,
            pushed_after=self.pushed_after,
            weekly_hours=self.weekly_hours,
            platform=self.platform,
            project_size=self.project_size,
        )


class QueryInterpretation(BaseModel):
    source: Literal["model", "rules"]
    model: str | None = None
    summary: str
    search_terms: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None

