from typing import Annotated

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_github_client
from packages.domain.search import SearchRequest, SearchResponse
from packages.github_client import GitHubClient
from packages.search import SearchService

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_repositories(
    request: SearchRequest,
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> SearchResponse:
    return await SearchService(client).search(request)

