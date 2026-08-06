from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_github_client
from packages.domain.search import SearchRequest, SearchResponse
from packages.github_client import GitHubClient
from packages.persistence import ProductPersistence
from packages.search import SearchService

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_repositories(
    request: SearchRequest,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
) -> SearchResponse:
    return await SearchService(client, ProductPersistence(session)).search(request)
