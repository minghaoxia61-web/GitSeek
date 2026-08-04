import asyncio
import base64

from packages.github_client.schemas import (
    GitHubCommunityProfile,
    GitHubContentItem,
    GitHubRepository,
)
from packages.investigation import RepositoryInvestigator


def _repository() -> GitHubRepository:
    return GitHubRepository.model_validate(
        {
            "id": 1,
            "name": "demo",
            "full_name": "example/demo",
            "owner": {"login": "example"},
            "description": "A documented FastAPI project",
            "html_url": "https://github.com/example/demo",
            "default_branch": "main",
            "language": "Python",
            "topics": ["fastapi"],
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 100,
            "forks_count": 5,
            "open_issues_count": 4,
            "archived": False,
            "pushed_at": "2026-08-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-08-01T00:00:00Z",
        }
    )


def _content(name: str, *, item_type: str = "file") -> GitHubContentItem:
    return GitHubContentItem(
        type=item_type,
        name=name,
        path=name,
        sha=f"sha-{name}",
        html_url=f"https://github.com/example/demo/blob/main/{name}",
    )


class StubInvestigationClient:
    async def get_repository(self, owner: str, repo: str) -> GitHubRepository:
        assert (owner, repo) == ("example", "demo")
        return _repository()

    async def get_community_profile(self, owner: str, repo: str) -> GitHubCommunityProfile:
        del owner, repo
        return GitHubCommunityProfile.model_validate(
            {
                "health_percentage": 90,
                "files": {
                    "readme": {"html_url": "https://github.com/example/demo/README.md"},
                    "contributing": {
                        "html_url": "https://github.com/example/demo/CONTRIBUTING.md"
                    },
                    "issue_template": {
                        "html_url": "https://github.com/example/demo/issues/new/choose"
                    },
                    "pull_request_template": {
                        "html_url": "https://github.com/example/demo/PULL_REQUEST_TEMPLATE.md"
                    },
                    "code_of_conduct": {
                        "html_url": "https://github.com/example/demo/CODE_OF_CONDUCT.md"
                    },
                    "license": {"html_url": "https://github.com/example/demo/LICENSE"},
                },
            }
        )

    async def list_repository_contents(
        self,
        owner: str,
        repo: str,
        *,
        path: str = "",
        ref: str | None = None,
    ) -> list[GitHubContentItem]:
        del owner, repo, ref
        if path == ".github/workflows":
            return [_content("ci.yml")]
        return [
            _content("README.md"),
            _content("pyproject.toml"),
            _content("uv.lock"),
            _content("tests", item_type="dir"),
            _content(".github", item_type="dir"),
            _content("Dockerfile"),
        ]

    async def get_readme(self, owner: str, repo: str) -> GitHubContentItem:
        del owner, repo
        text = "# Demo\n\n## Installation\n\nRun the project."
        return GitHubContentItem(
            type="file",
            name="README.md",
            path="README.md",
            sha="readme-sha",
            encoding="base64",
            content=base64.b64encode(text.encode()).decode(),
            html_url="https://github.com/example/demo/blob/main/README.md",
        )


def test_investigator_builds_traceable_engineering_signals() -> None:
    result = asyncio.run(
        RepositoryInvestigator(StubInvestigationClient()).investigate("example", "demo")
    )

    assert result.full_name == "example/demo"
    assert result.confidence == "high"
    assert result.signals.has_contributing is True
    assert result.signals.has_tests is True
    assert result.signals.has_ci is True
    assert result.signals.has_pyproject is True
    assert result.signals.readme_has_quickstart is True
    assert result.scores.documentation == 90
    assert result.scores.engineering == 100
    assert result.scores.learning_friendliness == 100
    assert all(item.source_url.startswith("https://") for item in result.evidence)

