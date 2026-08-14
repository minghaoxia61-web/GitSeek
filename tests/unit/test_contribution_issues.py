import asyncio

from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from packages.contribution import ContributionIssueService
from packages.github_client.schemas import GitHubIssue


class StubIssueClient:
    async def list_repository_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 100,
    ) -> list[GitHubIssue]:
        assert (owner, repo, state, per_page) == ("example", "demo", "open", 100)
        base = {
            "html_url": "https://github.com/example/demo/issues/1",
            "state": "open",
            "assignees": [],
            "comments": 2,
            "locked": False,
            "created_at": "2026-07-01T00:00:00Z",
            "updated_at": "2026-08-01T00:00:00Z",
        }
        return [
            GitHubIssue.model_validate(
                {
                    **base,
                    "number": 1,
                    "title": "Improve quick-start documentation",
                    "body": "Expected behavior and acceptance criteria. " * 12,
                    "labels": [{"name": "good first issue"}],
                }
            ),
            GitHubIssue.model_validate(
                {
                    **base,
                    "number": 2,
                    "title": "Already assigned",
                    "body": "Do work",
                    "labels": [{"name": "help wanted"}],
                    "assignees": [{"login": "maintainer"}],
                }
            ),
        ]


def test_issue_service_excludes_claimed_work_and_scores_beginner_issue() -> None:
    result = asyncio.run(
        ContributionIssueService(StubIssueClient()).recommend("example", "demo")
    )

    assert len(result.issues) == 1
    assert result.issues[0].difficulty == "easy"
    assert result.issues[0].score >= 90


async def override_issue_client():
    yield StubIssueClient()


class CountingIssueClient(StubIssueClient):
    def __init__(self) -> None:
        self.issue_calls = 0

    async def list_repository_issues(self, *args, **kwargs):
        self.issue_calls += 1
        return await super().list_repository_issues(*args, **kwargs)


def test_issue_endpoint_returns_only_actionable_work() -> None:
    app.dependency_overrides[get_github_client] = override_issue_client
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/repos/example/demo/issues?limit=3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["issues"][0]["number"] == 1


def test_issue_endpoint_reuses_recent_cache() -> None:
    github = CountingIssueClient()

    async def override():
        yield github

    app.dependency_overrides[get_github_client] = override
    try:
        with TestClient(app) as client:
            first = client.get("/api/v1/repos/example/demo/issues?limit=3")
            second = client.get("/api/v1/repos/example/demo/issues?limit=3")
            refreshed = client.get("/api/v1/repos/example/demo/issues?limit=3&refresh=true")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == second.status_code == refreshed.status_code == 200
    assert github.issue_calls == 2
