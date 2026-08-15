from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

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
REFRESH_INTERVALS = {
    ">=1000": timedelta(days=1),
    "100..999": timedelta(days=2),
    "10..99": timedelta(days=7),
    "1..9": timedelta(days=14),
}


def _select_refresh_cursors(
    cursors: list[IndexSyncCursor],
    *,
    count: int,
    now: datetime,
) -> list[IndexSyncCursor]:
    def last_success(cursor: IndexSyncCursor) -> datetime | None:
        value = cursor.last_success_at
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def interval(cursor: IndexSyncCursor) -> timedelta:
        return next(
            (
                duration
                for band, duration in REFRESH_INTERVALS.items()
                if f"stars:{band}" in cursor.query
            ),
            timedelta(days=7),
        )

    due = [
        cursor
        for cursor in cursors
        if last_success(cursor) is None or last_success(cursor) <= now - interval(cursor)
    ]
    ordered_due = sorted(
        due,
        key=lambda cursor: (
            last_success(cursor) is not None,
            interval(cursor).total_seconds(),
            last_success(cursor) or datetime.min.replace(tzinfo=UTC),
            cursor.id,
        ),
    )
    if len(ordered_due) >= count:
        return ordered_due[:count]
    selected_ids = {cursor.id for cursor in ordered_due}
    fallback = sorted(
        (cursor for cursor in cursors if cursor.id not in selected_ids),
        key=lambda cursor: last_success(cursor) or datetime.min.replace(tzinfo=UTC),
    )
    return [*ordered_due, *fallback][:count]


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

    indexed_count = (await run_in_threadpool(RepositoryIndex(session).status)).repository_count
    bootstrap = indexed_count < 3_000
    query_count = 4 if bootstrap else 2
    cursors = {
        cursor.query: cursor
        for cursor in await run_in_threadpool(
            session.scalars,
            select(IndexSyncCursor).where(IndexSyncCursor.query.in_(REFRESH_QUERIES)),
        )
    }
    for query in REFRESH_QUERIES:
        if query not in cursors:
            cursor = IndexSyncCursor(query=query)
            session.add(cursor)
            cursors[query] = cursor
    await run_in_threadpool(session.flush)
    selected_cursors = _select_refresh_cursors(
        list(cursors.values()),
        count=query_count,
        now=datetime.now(UTC),
    )
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
            await run_in_threadpool(session.rollback)
            cursor = await run_in_threadpool(
                session.scalar,
                select(IndexSyncCursor).where(IndexSyncCursor.query == cursor.query),
            )
            if cursor is not None:
                cursor.failure_count += 1
                cursor.last_error = str(exc)[:1000]
                await run_in_threadpool(session.commit)
            failed_queries.append(cursor.query if cursor is not None else "unknown")
            continue
        cursor.next_page = (
            1 if cursor.next_page >= 10 or stats.fetched == 0 else cursor.next_page + 1
        )
        cursor.last_success_at = utc_now()
        cursor.failure_count = 0
        cursor.last_error = None
        await run_in_threadpool(session.commit)
        fetched += stats.fetched
        created += stats.created
        updated += stats.updated
        snapshots_created += stats.snapshots_created
    pruned = await run_in_threadpool(synchronizer.prune_stale)
    return IndexRefreshResponse(
        queries=selected_queries,
        fetched=fetched,
        created=created,
        updated=updated,
        snapshots_created=snapshots_created,
        pruned=pruned,
        failed_queries=failed_queries,
        completed_at=datetime.now(UTC),
    )
