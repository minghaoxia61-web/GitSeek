from datetime import UTC, datetime
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_github_client
from packages.domain.index import IndexRefreshResponse
from packages.domain.settings import get_settings
from packages.github_client import GitHubClient
from packages.retrieval import RepositoryIndex
from workers.sync.repositories import RepositorySynchronizer

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

REFRESH_QUERIES = [
    "language:Python archived:false stars:>=10000",
    "language:Python archived:false stars:3000..9999",
    "language:Python archived:false stars:1000..2999",
    "language:Python archived:false stars:300..999",
    "language:Python archived:false stars:100..299",
    "language:Python archived:false stars:30..99",
    "language:Python archived:false stars:10..29",
    "language:Python archived:false stars:1..9",
    "language:Python archived:false stars:0",
]


@router.get("/refresh-index", response_model=IndexRefreshResponse)
async def refresh_repository_index(
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> IndexRefreshResponse:
    secret = get_settings().cron_secret
    secret_value = secret.get_secret_value() if secret is not None else ""
    if len(secret_value) < 16:
        raise HTTPException(status_code=503, detail="Index refresh is not configured")
    expected = f"Bearer {secret_value}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid refresh credential")

    day = datetime.now(UTC).toordinal()
    indexed_count = RepositoryIndex(session).status().repository_count
    bootstrap = indexed_count < 3_000
    query_count = 4 if bootstrap else 2
    selected_queries = [
        REFRESH_QUERIES[(day + offset) % len(REFRESH_QUERIES)]
        for offset in range(query_count)
    ]
    page = 1 + (day // len(REFRESH_QUERIES)) % 5 if bootstrap else 1
    synchronizer = RepositorySynchronizer(session, client)
    fetched = created = updated = 0
    for query in selected_queries:
        stats = await synchronizer.sync_query(query, pages=1, start_page=page)
        fetched += stats.fetched
        created += stats.created
        updated += stats.updated
    return IndexRefreshResponse(
        queries=selected_queries,
        fetched=fetched,
        created=created,
        updated=updated,
        completed_at=datetime.now(UTC),
    )
