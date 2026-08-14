from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_github_client
from packages.contribution import ContributionIssueService
from packages.domain.contribution import ContributionIssueResponse
from packages.domain.investigation import RepositoryInvestigation
from packages.github_client import (
    GitHubAPIError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from packages.investigation import RepositoryInvestigator
from packages.persistence import ProductPersistence

router = APIRouter(prefix="/api/v1/repos", tags=["repositories"])


@router.get("/{owner}/{repo}/issues", response_model=ContributionIssueResponse)
async def recommend_contribution_issues(
    owner: str,
    repo: str,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
    limit: int = 5,
    refresh: bool = False,
) -> ContributionIssueResponse:
    bounded_limit = max(1, min(limit, 10))
    persistence = ProductPersistence(session)
    if not refresh:
        cached = persistence.load_cached_issues(
            f"{owner}/{repo}",
            limit=bounded_limit,
        )
        if cached is not None:
            return cached
    try:
        response = await ContributionIssueService(client).recommend(
            owner,
            repo,
            limit=bounded_limit,
        )
        persistence.save_issues(response)
        persistence.save_issue_cache(response)
        return response
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository not found") from exc
    except GitHubRateLimitError as exc:
        stale = persistence.load_cached_issues(
            f"{owner}/{repo}",
            limit=bounded_limit,
            max_age=None,
        )
        if stale is not None:
            return stale
        raise HTTPException(
            status_code=429,
            detail={"message": "GitHub rate limit exceeded", "reset_at": exc.reset_at},
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail="GitHub issue lookup failed") from exc


@router.get("/{owner}/{repo}/investigate", response_model=RepositoryInvestigation)
async def investigate_repository(
    owner: str,
    repo: str,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
    refresh: bool = False,
) -> RepositoryInvestigation:
    persistence = ProductPersistence(session)
    if not refresh:
        cached = persistence.load_cached_investigation(f"{owner}/{repo}")
        if cached is not None:
            return cached
    try:
        response = await RepositoryInvestigator(client).investigate(owner, repo)
        persistence.save_investigation(response)
        return response
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository not found") from exc
    except GitHubRateLimitError as exc:
        stale = persistence.load_cached_investigation(f"{owner}/{repo}", max_age=None)
        if stale is not None:
            return stale
        raise HTTPException(
            status_code=429,
            detail={"message": "GitHub rate limit exceeded", "reset_at": exc.reset_at},
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail="GitHub investigation failed") from exc
