import asyncio

from fastapi.testclient import TestClient

from apps.api.dependencies import get_github_client
from apps.api.main import app
from packages.contribution import ContributionIssueService
from packages.github_client.schemas import GitHubIssue, GitHubRepository, GitHubUser


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


class ProfileMatchClient(StubIssueClient):
    async def get_user(self, username: str) -> GitHubUser:
        assert username == "learner"
        return GitHubUser.model_validate(
            {
                "login": "learner",
                "name": "Open Source Learner",
                "html_url": "https://github.com/learner",
                "public_repos": 8,
                "followers": 3,
            }
        )

    async def list_user_repositories(
        self,
        username: str,
        *,
        per_page: int = 100,
    ) -> list[GitHubRepository]:
        assert (username, per_page) == ("learner", 100)
        return [self._repository("learner/api-demo", "Python", ["fastapi", "pytest"])]

    async def get_repository(self, owner: str, repo: str) -> GitHubRepository:
        assert (owner, repo) == ("example", "demo")
        return self._repository("example/demo", "Python", ["fastapi", "api"])

    @staticmethod
    def _repository(full_name: str, language: str, topics: list[str]) -> GitHubRepository:
        owner, name = full_name.split("/", 1)
        return GitHubRepository.model_validate(
            {
                "id": abs(hash(full_name)) % 100000,
                "name": name,
                "full_name": full_name,
                "owner": {"login": owner},
                "description": "FastAPI testing project",
                "html_url": f"https://github.com/{full_name}",
                "language": language,
                "topics": topics,
                "stargazers_count": 10,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2026-08-01T00:00:00Z",
            }
        )


def test_issue_match_uses_public_profile_skills() -> None:
    result = asyncio.run(
        ContributionIssueService(ProfileMatchClient()).match_for_user(
            "example",
            "demo",
            "learner",
        )
    )

    assert result.profile.experience_level == "intermediate"
    assert result.profile.languages == {"Python": 1}
    assert result.issues[0].fit_score >= result.issues[0].score * 0.6
    assert "python" in result.issues[0].matched_skills
    assert len(result.issues[0].start_checklist) == 3


def test_issue_match_endpoint_returns_profile_and_fit() -> None:
    async def override():
        yield ProfileMatchClient()

    app.dependency_overrides[get_github_client] = override
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/repos/example/demo/issue-matches/learner")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["username"] == "learner"
    assert payload["issues"][0]["matched_skills"]
