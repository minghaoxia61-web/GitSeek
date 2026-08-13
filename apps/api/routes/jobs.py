from datetime import UTC, datetime
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_github_client
from packages.domain.index import IndexRefreshResponse
from packages.domain.models import IndexSyncCursor
from packages.domain.models.base import utc_now
from packages.domain.settings import get_settings
from packages.github_client import GitHubAPIError, GitHubClient
from packages.retrieval import RepositoryIndex
from workers.sync.repositories import RepositorySynchronizer

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

REFRESH_LANGUAGES = ("Python", "TypeScript", "JavaScript", "Java", "Go", "Rust")
REFRESH_STAR_BANDS = (">=1000", "100..999", "10..99", "1..9")
REFRESH_QUERIES = [
    f"language:{language} archived:false stars:{stars}"
    for language in REFRESH_LANGUAGES
    for stars in REFRESH_STAR_BANDS
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

    indexed_count = RepositoryIndex(session).status().repository_count
    bootstrap = indexed_count < 3_000
    query_count = 4 if bootstrap else 2
    cursors = {
        cursor.query: cursor
        for cursor in session.scalars(
            select(IndexSyncCursor).where(IndexSyncCursor.query.in_(REFRESH_QUERIES))
        )
    }
    for query in REFRESH_QUERIES:
        if query not in cursors:
            cursor = IndexSyncCursor(query=query)
            session.add(cursor)
            cursors[query] = cursor
    session.flush()
    selected_cursors = sorted(
        cursors.values(),
        key=lambda cursor: (
            cursor.last_success_at is not None,
            cursor.last_success_at or datetime.min.replace(tzinfo=UTC),
            cursor.id,
        ),
    )[:query_count]
    selected_queries = [cursor.query for cursor in selected_cursors]
    synchronizer = RepositorySynchronizer(session, client)
    fetched = created = updated = snapshots_created = 0
    failed_queries: list[str] = []
    for cursor in selected_cursors:
        try:
            stats = await synchronizer.sync_query(
                cursor.query,
                pages=1,
                start_page=cursor.next_page,
            )
        except GitHubAPIError as exc:
            session.rollback()
            cursor = session.scalar(
                select(IndexSyncCursor).where(IndexSyncCursor.query == cursor.query)
            )
            if cursor is not None:
                cursor.failure_count += 1
                cursor.last_error = str(exc)[:1000]
                session.commit()
            failed_queries.append(cursor.query if cursor is not None else "unknown")
            continue
        cursor.next_page = (
            1 if cursor.next_page >= 10 or stats.fetched == 0 else cursor.next_page + 1
        )
        cursor.last_success_at = utc_now()
        cursor.failure_count = 0
        cursor.last_error = None
        session.commit()
        fetched += stats.fetched
        created += stats.created
        updated += stats.updated
        snapshots_created += stats.snapshots_created
    return IndexRefreshResponse(
        queries=selected_queries,
        fetched=fetched,
        created=created,
        updated=updated,
        snapshots_created=snapshots_created,
        failed_queries=failed_queries,
        completed_at=datetime.now(UTC),
    )
