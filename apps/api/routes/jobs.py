from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_github_client
from packages.domain.index import IndexRefreshResponse
from packages.domain.settings import get_settings
from packages.github_client import GitHubClient
from workers.sync.repositories import refresh_index

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def require_refresh_authorization(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    secret = get_settings().cron_secret
    secret_value = secret.get_secret_value() if secret is not None else ""
    if len(secret_value) < 16:
        raise HTTPException(status_code=503, detail="Index refresh is not configured")
    expected = f"Bearer {secret_value}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid refresh credential")


@router.get(
    "/refresh-index",
    response_model=IndexRefreshResponse,
    dependencies=[Depends(require_refresh_authorization)],
)
async def refresh_repository_index(
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
) -> IndexRefreshResponse | JSONResponse:
    result = await refresh_index(session, client)
    if result.failed_queries:
        return JSONResponse(status_code=503, content=result.model_dump(mode="json"))
    return result
