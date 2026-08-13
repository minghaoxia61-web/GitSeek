from datetime import UTC, date, datetime

from packages.domain.search import SearchConstraints
from packages.github_client.schemas import GitHubRepository
from packages.ranking import rank_repositories


def _repository(
    *,
    github_id: int,
    name: str,
    license_spdx: str | None,
    archived: bool = False,
    pushed_at: str = "2026-07-20T00:00:00Z",
    stars: int = 100,
    description: str = "FastAPI starter with typed APIs",
    topics: list[str] | None = None,
) -> GitHubRepository:
    return GitHubRepository.model_validate(
        {
            "id": github_id,
            "name": name,
            "full_name": f"example/{name}",
            "owner": {"login": "example"},
            "description": description,
            "html_url": f"https://github.com/example/{name}",
            "default_branch": "main",
            "language": "Python",
            "topics": topics if topics is not None else ["fastapi", "python"],
            "license": {"spdx_id": license_spdx} if license_spdx else None,
            "stargazers_count": stars,
            "forks_count": 5,
            "open_issues_count": 3,
            "archived": archived,
            "pushed_at": pushed_at,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": pushed_at,
        }
    )


def test_ranking_enforces_hard_constraints_before_scoring() -> None:
    constraints = SearchConstraints(
        technologies=["FastAPI"],
        licenses=["MIT"],
        pushed_after=date(2026, 2, 1),
    )
    repositories = [
        _repository(github_id=1, name="eligible", license_spdx="MIT", stars=500),
        _repository(github_id=2, name="wrong-license", license_spdx="GPL-3.0", stars=50000),
        _repository(github_id=3, name="archived", license_spdx="MIT", archived=True),
        _repository(
            github_id=4,
            name="stale",
            license_spdx="MIT",
            pushed_at="2025-01-01T00:00:00Z",
        ),
    ]

    results, eligible_count = rank_repositories(
        repositories,
        constraints,
        limit=10,
        now=datetime(2026, 8, 3, tzinfo=UTC),
    )

    assert eligible_count == 1
    assert [result.full_name for result in results] == ["example/eligible"]
    assert results[0].constraint_match["license"] == "MATCH"
    assert results[0].score_breakdown["relevance"] == 35.0


def test_specific_search_terms_remove_popular_but_unrelated_candidates() -> None:
    constraints = SearchConstraints(language="Python")
    repositories = [
        _repository(
            github_id=1,
            name="httpx-client",
            license_spdx="MIT",
            description="An async HTTP client for Python",
            topics=["httpx", "asyncio"],
        ),
        _repository(
            github_id=2,
            name="popular-framework",
            license_spdx="MIT",
            stars=200_000,
            description="A popular application framework",
            topics=["python", "framework"],
        ),
    ]

    results, eligible_count = rank_repositories(
        repositories,
        constraints,
        limit=10,
        query="Python async HTTP client httpx aiohttp",
        required_search_terms=["httpx", "aiohttp", "async http"],
    )

    assert eligible_count == 1
    assert [result.full_name for result in results] == ["example/httpx-client"]
