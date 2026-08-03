from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GitHubOwner(BaseModel):
    login: str


class GitHubLicense(BaseModel):
    spdx_id: str | None = None


class GitHubRepository(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    full_name: str
    owner: GitHubOwner
    description: str | None = None
    html_url: str
    default_branch: str = "main"
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    license: GitHubLicense | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    archived: bool = False
    pushed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GitHubSearchResult(BaseModel):
    total_count: int
    incomplete_results: bool
    items: list[GitHubRepository]


class GitHubSearchPage(BaseModel):
    result: GitHubSearchResult
    etag: str | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset: int | None = None

