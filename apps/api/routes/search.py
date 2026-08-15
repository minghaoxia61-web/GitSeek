from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_embedding_client, get_github_client
from packages.domain.index import RepositoryIndexStatus
from packages.domain.search import SearchRequest, SearchResponse, TrendingResponse
from packages.embeddings import ExternalEmbeddingService, OpenAIEmbeddingClient
from packages.github_client import GitHubAPIError, GitHubClient, GitHubRateLimitError
from packages.persistence import ProductPersistence
from packages.retrieval import RepositoryIndex
from packages.search import SearchService, TrendingService

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/trending", response_model=TrendingResponse)
async def trending_repositories(
    client: Annotated[GitHubClient, Depends(get_github_client)],
    response: Response,
    days: Annotated[int, Query()] = 7,
    limit: Annotated[int, Query(ge=1, le=10)] = 6,
) -> TrendingResponse:
    if days not in (7, 30):
        raise HTTPException(status_code=422, detail="days must be either 7 or 30")
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=900"
    try:
        return await TrendingService(client).list(days=days, limit=limit)
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail={"message": "GitHub rate limit exceeded", "reset_at": exc.reset_at},
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail="GitHub trending lookup failed") from exc


@router.get("/index/status", response_model=RepositoryIndexStatus)
def repository_index_status(
    session: Annotated[Session, Depends(get_db_session)],
) -> RepositoryIndexStatus:
    return RepositoryIndex(session).status()


@router.post("/search", response_model=SearchResponse)
async def search_repositories(
    request: SearchRequest,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
    embedding_client: Annotated[
        OpenAIEmbeddingClient | None,
        Depends(get_embedding_client),
    ],
) -> SearchResponse:
    return await SearchService(
        client,
        ProductPersistence(session),
        RepositoryIndex(session),
        (
            ExternalEmbeddingService(session, embedding_client)
            if embedding_client is not None
            else None
        ),
    ).search(request)
