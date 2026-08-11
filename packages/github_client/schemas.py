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


class GitHubContentItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    name: str
    path: str
    sha: str
    size: int = 0
    html_url: str | None = None
    download_url: str | None = None
    encoding: str | None = None
    content: str | None = None


class GitHubCommunityFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    html_url: str | None = None
    url: str | None = None


class GitHubCommunityFiles(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code_of_conduct: GitHubCommunityFile | None = None
    code_of_conduct_file: GitHubCommunityFile | None = None
    contributing: GitHubCommunityFile | None = None
    issue_template: GitHubCommunityFile | None = None
    pull_request_template: GitHubCommunityFile | None = None
    license: GitHubCommunityFile | None = None
    readme: GitHubCommunityFile | None = None
    security_policy: GitHubCommunityFile | None = None


class GitHubCommunityProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    health_percentage: int
    description: str | None = None
    files: GitHubCommunityFiles
    updated_at: datetime | None = None


class GitHubLabel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class GitHubAssignee(BaseModel):
    model_config = ConfigDict(extra="ignore")

    login: str


class GitHubIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    body: str | None = None
    html_url: str
    state: str
    labels: list[GitHubLabel] = Field(default_factory=list)
    assignees: list[GitHubAssignee] = Field(default_factory=list)
    comments: int = 0
    locked: bool = False
    created_at: datetime
    updated_at: datetime
    pull_request: dict[str, object] | None = None


class GitHubRelease(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tag_name: str
    html_url: str
    draft: bool = False
    prerelease: bool = False
    published_at: datetime | None = None


class GitHubPullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int
    html_url: str
    state: str
    created_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None


class GitHubContributor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    login: str
    contributions: int = 0
