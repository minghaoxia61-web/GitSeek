from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session
from packages.domain.saved import SavedRepositoryList, SaveRepositoryRequest
from packages.persistence import ProductPersistence

router = APIRouter(prefix="/api/v1/saved", tags=["saved repositories"])


@router.get("", response_model=SavedRepositoryList)
async def list_saved_repositories(
    session: Annotated[Session, Depends(get_db_session)],
    device_id: str = Query(min_length=8, max_length=64),
) -> SavedRepositoryList:
    repositories = ProductPersistence(session).list_saved_repositories(device_id)
    if repositories is None:
        raise HTTPException(
            status_code=503,
            detail="Saved repositories are temporarily unavailable",
        )
    return SavedRepositoryList(device_id=device_id, repositories=repositories)


@router.post("", response_model=SavedRepositoryList, status_code=201)
async def save_repository(
    request: SaveRepositoryRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> SavedRepositoryList:
    repositories = ProductPersistence(session).save_repository(
        request.device_id,
        request.repository,
    )
    if repositories is None:
        raise HTTPException(
            status_code=503,
            detail="Saved repositories are temporarily unavailable",
        )
    return SavedRepositoryList(device_id=request.device_id, repositories=repositories)


@router.delete("/{owner}/{repo}", response_model=SavedRepositoryList)
async def delete_saved_repository(
    owner: str,
    repo: str,
    session: Annotated[Session, Depends(get_db_session)],
    device_id: str = Query(min_length=8, max_length=64),
) -> SavedRepositoryList:
    repositories = ProductPersistence(session).delete_saved_repository(
        device_id,
        f"{owner}/{repo}",
    )
    if repositories is None:
        raise HTTPException(
            status_code=503,
            detail="Saved repositories are temporarily unavailable",
        )
    return SavedRepositoryList(device_id=device_id, repositories=repositories)
