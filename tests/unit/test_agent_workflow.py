import asyncio
import base64

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from packages.agents import AgentWorkflow
from packages.domain.agent import AgentRunRequest
from packages.domain.models import AgentRunRecord, AgentStepRecord, Base
from packages.domain.query_plan import ModelQueryPlan
from packages.github_client.schemas import (
    GitHubCommunityProfile,
    GitHubContentItem,
    GitHubRepository,
    GitHubSearchPage,
)
from packages.persistence import ProductPersistence
from packages.retrieval import RepositoryIndex


class AgentStubClient:
    repository = GitHubRepository.model_validate(
        {
            "id": 1,
            "name": "fastapi-demo",
            "full_name": "example/fastapi-demo",
            "owner": {"login": "example"},
            "description": "A FastAPI learning project",
            "html_url": "https://github.com/example/fastapi-demo",
            "default_branch": "main",
            "language": "Python",
            "topics": ["fastapi"],
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 100,
            "forks_count": 10,
            "open_issues_count": 4,
            "archived": False,
            "pushed_at": "2026-08-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-08-01T00:00:00Z",
        }
    )

    async def search_repositories(self, *args, **kwargs) -> GitHubSearchPage:
        del args, kwargs
        return GitHubSearchPage.model_validate(
            {
                "result": {
                    "total_count": 1,
                    "incomplete_results": False,
                    "items": [self.repository.model_dump(mode="json")],
                }
            }
        )

    async def get_repository(self, owner: str, repo: str) -> GitHubRepository:
        assert (owner, repo) == ("example", "fastapi-demo")
        return self.repository

    async def get_community_profile(self, *args) -> GitHubCommunityProfile:
        del args
        return GitHubCommunityProfile.model_validate(
            {
                "health_percentage": 90,
                "files": {
                    "readme": {"html_url": "https://github.com/example/fastapi-demo"},
                    "contributing": {
                        "html_url": "https://github.com/example/fastapi-demo/CONTRIBUTING.md"
                    },
                    "license": {"html_url": "https://github.com/example/fastapi-demo/LICENSE"},
                },
            }
        )

    async def list_repository_contents(
        self,
        *args,
        path: str = "",
        **kwargs,
    ) -> list[GitHubContentItem]:
        del args, kwargs
        if path == ".github/workflows":
            return [
                GitHubContentItem.model_validate(
                    {
                        "type": "file",
                        "name": "test.yml",
                        "path": ".github/workflows/test.yml",
                        "sha": "ci",
                    }
                )
            ]
        return [
            GitHubContentItem.model_validate(
                {"type": "dir", "name": name, "path": name, "sha": name}
            )
            for name in ("tests", ".github")
        ] + [
            GitHubContentItem.model_validate(
                {
                    "type": "file",
                    "name": "pyproject.toml",
                    "path": "pyproject.toml",
                    "sha": "pyproject",
                }
            )
        ]

    async def get_readme(self, *args) -> GitHubContentItem:
        del args
        content = base64.b64encode(b"## Installation\nRun the project").decode()
        return GitHubContentItem.model_validate(
            {
                "type": "file",
                "name": "README.md",
                "path": "README.md",
                "sha": "readme",
                "encoding": "base64",
                "content": content,
                "html_url": "https://github.com/example/fastapi-demo#readme",
            }
        )

    async def list_releases(self, *args, **kwargs) -> list:
        del args, kwargs
        return []

    async def list_pull_requests(self, *args, **kwargs) -> list:
        del args, kwargs
        return []

    async def list_contributors(self, *args, **kwargs) -> list:
        del args, kwargs
        return []


class StubQueryPlanner:
    model = "test-model"

    async def plan(self, query: str) -> ModelQueryPlan:
        assert "FastAPI" in query
        return ModelQueryPlan(
            summary="寻找适合初学者学习的 FastAPI 仓库",
            language="Python",
            technologies=["FastAPI"],
            github_terms=["FastAPI", "beginner"],
            licenses=["MIT"],
            purpose="learning",
        )


class SearchOnlyAgentClient(AgentStubClient):
    async def get_repository(self, owner: str, repo: str) -> GitHubRepository:
        del owner, repo
        raise AssertionError("fast search must not start repository investigation")


def test_agent_runs_bounded_workflow_and_persists_trace() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        persistence = ProductPersistence(session)
        response = asyncio.run(
            AgentWorkflow(
                AgentStubClient(),
                persistence,
                RepositoryIndex(session),
                StubQueryPlanner(),
            ).run(
                AgentRunRequest(
                    query="适合初学者学习的 FastAPI 项目，MIT 许可证",
                    investigate_limit=1,
                )
            )
        )

        assert response.status == "succeeded"
        assert response.interpretation.source == "model"
        assert response.interpretation.model == "test-model"
        assert response.search.generated_github_query.startswith("FastAPI language:Python")
        assert "beginner language:Python" in response.search.generated_github_query
        assert [step.node for step in response.steps] == [
            "parse_query",
            "plan_search",
            "retrieve_candidates",
            "investigate_repositories",
            "verify_evidence",
        ]
        assert response.verification[0].support_ratio == 1
        assert response.investigations[0].signals.has_tests is True
        assert session.scalar(select(func.count(AgentRunRecord.id))) == 1
        assert session.scalar(select(func.count(AgentStepRecord.id))) == 5


def test_agent_can_return_without_blocking_on_deep_investigation() -> None:
    response = asyncio.run(
        AgentWorkflow(SearchOnlyAgentClient(), query_planner=StubQueryPlanner()).run(
            AgentRunRequest(
                query="适合初学者学习的 FastAPI 项目，MIT 许可证",
                investigate_limit=0,
            )
        )
    )

    assert response.search.results
    assert response.investigations == []
    assert response.verification == []
    investigation_step = next(
        step for step in response.steps if step.node == "investigate_repositories"
    )
    assert "打开项目档案" in investigation_step.summary


def test_agent_emits_each_completed_step_in_order() -> None:
    emitted = []

    async def run():
        async def progress(step):
            emitted.append(step.node)

        return await AgentWorkflow(
            SearchOnlyAgentClient(), query_planner=StubQueryPlanner()
        ).run(
            AgentRunRequest(query="FastAPI beginner project", investigate_limit=0),
            progress=progress,
        )

    response = asyncio.run(run())
    assert emitted == [step.node for step in response.steps]
