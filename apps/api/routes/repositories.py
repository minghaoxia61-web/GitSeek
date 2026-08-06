from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies import get_github_client
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

router = APIRouter(prefix="/api/v1/repos", tags=["repositories"])


@router.get("/{owner}/{repo}/issues", response_model=ContributionIssueResponse)
async def recommend_contribution_issues(
    owner: str,
    repo: str,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    limit: int = 5,
) -> ContributionIssueResponse:
    try:
        return await ContributionIssueService(client).recommend(
            owner,
            repo,
            limit=max(1, min(limit, 10)),
        )
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository not found") from exc
    except GitHubRateLimitError as exc:
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
) -> RepositoryInvestigation:
    try:
        return await RepositoryInvestigator(client).investigate(owner, repo)
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repository not found") from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail={"message": "GitHub rate limit exceeded", "reset_at": exc.reset_at},
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail="GitHub investigation failed") from exc
