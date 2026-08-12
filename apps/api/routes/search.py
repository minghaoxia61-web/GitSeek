from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_embedding_client, get_github_client
from packages.domain.index import RepositoryIndexStatus
from packages.domain.search import SearchRequest, SearchResponse
from packages.embeddings import ExternalEmbeddingService, OpenAIEmbeddingClient
from packages.github_client import GitHubClient
from packages.persistence import ProductPersistence
from packages.retrieval import RepositoryIndex
from packages.search import SearchService

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/index/status", response_model=RepositoryIndexStatus)
async def repository_index_status(
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
