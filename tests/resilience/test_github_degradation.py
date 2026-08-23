import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.dependencies import get_github_client
from apps.api.main import app
from packages.contribution import ContributionIssueService
from packages.domain.models import Base
from packages.domain.search import SearchRequest
from packages.github_client.schemas import GitHubIssue, GitHubIssueComment
from packages.resilience import FaultInjectingClient, FaultRule
from packages.retrieval import RepositoryIndex
from packages.search import SearchService
from tests.unit.test_repository_index import make_repository


class ScenarioGitHubClient:
    async def list_repository_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 100,
    ) -> list[GitHubIssue]:
        del owner, repo
        assert (state, per_page) == ("open", 100)
        return [
            GitHubIssue.model_validate(
                {
                    "number": 7,
                    "title": "Document the local setup",
                    "body": "Reproduction steps and acceptance criteria. " * 10,
                    "html_url": "https://github.com/fault/demo/issues/7",
                    "state": "open",
                    "labels": [{"name": "good first issue"}],
                    "assignees": [],
                    "comments": 1,
                    "locked": False,
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-10T00:00:00Z",
                    "user": {"login": "reporter"},
                }
            )
        ]

    async def list_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        per_page: int = 30,
    ) -> list[GitHubIssueComment]:
        del owner, repo
        assert (issue_number, per_page) == (7, 30)
        return [
            GitHubIssueComment.model_validate(
                {
                    "id": 71,
                    "html_url": "https://github.com/fault/demo/issues/7#issuecomment-71",
                    "created_at": "2026-08-02T00:00:00Z",
                    "user": {"login": "maintainer"},
                    "author_association": "MEMBER",
                }
            )
        ]

    async def search_repositories(self, *_args, **_kwargs):
        raise AssertionError("fault rule should fire before the delegate")


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("rate_limit", "github_rate_limit"),
        ("timeout", "github_unavailable"),
    ],
)
def test_issue_refresh_falls_back_to_explicit_stale_cache(kind: str, reason: str) -> None:
    github = FaultInjectingClient(
        ScenarioGitHubClient(),
        FaultRule(method="list_repository_issues", kind=kind, fail_on_calls=(2,)),
    )

    async def override():
        yield github

    app.dependency_overrides[get_github_client] = override
    owner = f"fault-{kind}"
    try:
        with TestClient(app) as client:
            first = client.get(f"/api/v1/repos/{owner}/demo/issues?refresh=true")
            degraded = client.get(f"/api/v1/repos/{owner}/demo/issues?refresh=true")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == degraded.status_code == 200
    assert first.json()["data_status"] == "fresh"
    assert degraded.json()["data_status"] == "stale"
    assert degraded.json()["degradation_reason"] == reason
    assert degraded.json()["issues"][0]["number"] == 7


def test_issue_comment_failure_isolated_from_candidate_list() -> None:
    github = FaultInjectingClient(
        ScenarioGitHubClient(),
        FaultRule(method="list_issue_comments", kind="timeout"),
    )

    response = asyncio.run(ContributionIssueService(github).recommend("fault", "demo"))

    assert len(response.issues) == 1
    assert response.issues[0].response_status == "unknown"
    assert github.call_count("list_issue_comments") == 1


def test_search_timeout_preserves_local_index_results() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(make_repository())
            session.commit()
            github = FaultInjectingClient(
                ScenarioGitHubClient(),
                FaultRule(
                    method="search_repositories",
                    kind="timeout",
                    fail_on_calls=(1, 2, 3),
                ),
            )
            response = asyncio.run(
                SearchService(github, repository_index=RepositoryIndex(session)).search(
                    SearchRequest(query="FastAPI learning service", live_query_limit=3)
                )
            )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert response.retrieval.github_status == "unavailable"
    assert response.results[0].full_name == "example/fastapi-indexed"
    assert response.results[0].retrieval_sources == ["local_index"]
