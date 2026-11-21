import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from packages.database import create_db_engine, create_session_factory
from packages.domain.index import IndexRefreshResponse
from packages.domain.models import IndexSyncCursor, Repository, RepositorySnapshot
from packages.domain.models.base import utc_now
from packages.domain.settings import get_settings
from packages.github_client import GitHubAPIError, GitHubClient
from packages.github_client.schemas import GitHubRepository


@dataclass(frozen=True)
class SyncStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    snapshots_created: int = 0


class RepositorySynchronizer:
    def __init__(self, session: Session, client: GitHubClient) -> None:
        self._session = session
        self._client = client

    async def sync_query(
        self,
        query: str,
        *,
        pages: int = 1,
        start_page: int = 1,
        commit: bool = True,
    ) -> SyncStats:
        if pages < 1:
            raise ValueError("pages must be at least 1")
        if start_page < 1:
            raise ValueError("start_page must be at least 1")

        fetched = created = updated = snapshots_created = 0
        for page_number in range(start_page, start_page + pages):
            page = await self._client.search_repositories(query, page=page_number)
            if not page.result.items:
                break

            github_ids = [item.id for item in page.result.items]
            existing_repos = {
                repo.github_id: repo
                for repo in self._session.scalars(
                    select(Repository).where(Repository.github_id.in_(github_ids))
                )
            }

            for item in page.result.items:
                was_created = self._upsert(
                    item, source_etag=page.etag, existing=existing_repos.get(item.id)
                )
                fetched += 1
                created += int(was_created)
                updated += int(not was_created)

            self._session.flush()
            records = {
                record.github_id: record
                for record in self._session.scalars(
                    select(Repository).where(Repository.github_id.in_(github_ids))
                )
            }
            repo_ids = [records[item.id].id for item in page.result.items]
            all_snapshots = self._session.scalars(
                select(RepositorySnapshot)
                .where(RepositorySnapshot.repo_id.in_(repo_ids))
                .order_by(RepositorySnapshot.repo_id, RepositorySnapshot.fetched_at.desc())
            )
            latest_metrics_by_repo: dict[int, dict] = {}
            for snapshot in all_snapshots:
                if snapshot.repo_id not in latest_metrics_by_repo:
                    latest_metrics_by_repo[snapshot.repo_id] = snapshot.metrics_json

            for item in page.result.items:
                metrics = {
                    "stars": item.stargazers_count,
                    "forks": item.forks_count,
                    "open_issues": item.open_issues_count,
                    "archived": item.archived,
                    "pushed_at": item.pushed_at.isoformat() if item.pushed_at else None,
                }
                repo_id = records[item.id].id
                latest_metrics = latest_metrics_by_repo.get(repo_id)
                if latest_metrics != metrics:
                    self._session.add(
                        RepositorySnapshot(
                            repo_id=records[item.id].id,
                            metrics_json=metrics,
                        )
                    )
                    snapshots_created += 1

        if commit:
            self._session.commit()
        return SyncStats(
            fetched=fetched,
            created=created,
            updated=updated,
            snapshots_created=snapshots_created,
        )

    def _upsert(
        self, item: GitHubRepository, *, source_etag: str | None, existing: Repository | None = None
    ) -> bool:
        repository = existing
        was_created = repository is None
        if repository is None:
            repository = Repository(
                github_id=item.id,
                full_name=item.full_name,
                owner=item.owner.login,
                name=item.name,
                description=item.description,
                html_url=item.html_url,
                default_branch=item.default_branch,
                primary_language=item.language,
                topics=item.topics,
                license_spdx=item.license.spdx_id if item.license else None,
                stars=item.stargazers_count,
                forks=item.forks_count,
                open_issues=item.open_issues_count,
                archived=item.archived,
                pushed_at=item.pushed_at,
                github_created_at=item.created_at,
                github_updated_at=item.updated_at,
                fetched_at=utc_now(),
                source_etag=source_etag,
                raw_metadata=item.model_dump(mode="json"),
            )
            self._session.add(repository)
        else:
            repository.full_name = item.full_name
            repository.owner = item.owner.login
            repository.name = item.name
            repository.description = item.description
            repository.html_url = item.html_url
            repository.default_branch = item.default_branch
            repository.primary_language = item.language
            repository.topics = item.topics
            repository.license_spdx = item.license.spdx_id if item.license else None
            repository.stars = item.stargazers_count
            repository.forks = item.forks_count
            repository.open_issues = item.open_issues_count
            repository.archived = item.archived
            repository.pushed_at = item.pushed_at
            repository.github_updated_at = item.updated_at
            repository.fetched_at = utc_now()
            repository.source_etag = source_etag
            repository.raw_metadata = item.model_dump(mode="json")

        return was_created

    def prune_stale(self, *, now: datetime | None = None) -> int:
        reference_time = now or datetime.now(UTC)
        archived_cutoff = reference_time - timedelta(days=30)
        stale_cutoff = reference_time - timedelta(days=90)
        inactive_cutoff = reference_time - timedelta(days=365)
        result = self._session.execute(
            delete(Repository).where(
                or_(
                    and_(Repository.archived.is_(True), Repository.fetched_at < archived_cutoff),
                    and_(
                        Repository.stars < 10,
                        Repository.fetched_at < stale_cutoff,
                        or_(
                            Repository.pushed_at.is_(None),
                            Repository.pushed_at < inactive_cutoff,
                        ),
                    ),
                )
            )
        )
        self._session.commit()
        return int(result.rowcount or 0)


REFRESH_LANGUAGES = ("Python", "TypeScript", "JavaScript", "Java", "Go", "Rust")
REFRESH_INTERVALS = {
    ">=1000": timedelta(days=1),
    "100..999": timedelta(days=2),
    "10..99": timedelta(days=7),
    "1..9": timedelta(days=14),
}
REFRESH_QUERIES = [
    f"language:{language} archived:false stars:{stars}"
    for language in REFRESH_LANGUAGES
    for stars in REFRESH_INTERVALS
]


def _select_refresh_cursors(
    cursors: list[IndexSyncCursor], *, count: int, now: datetime
) -> list[IndexSyncCursor]:
    def last_success(cursor: IndexSyncCursor) -> datetime:
        value = cursor.last_success_at or datetime.min.replace(tzinfo=UTC)
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    def due_at(cursor: IndexSyncCursor) -> datetime:
        interval = next(
            (value for band, value in REFRESH_INTERVALS.items() if f"stars:{band}" in cursor.query),
            timedelta(days=7),
        )
        return last_success(cursor) + interval

    due = sorted(
        (cursor for cursor in cursors if due_at(cursor) <= now),
        key=lambda cursor: (due_at(cursor), cursor.id),
    )
    selected_ids = {cursor.id for cursor in due}
    remaining = sorted(
        (cursor for cursor in cursors if cursor.id not in selected_ids),
        key=lambda cursor: (last_success(cursor), cursor.id),
    )
    return [*due, *remaining][:count]


async def refresh_index(
    session: Session, client: GitHubClient, *, timeout_s: float = 45.0
) -> IndexRefreshResponse:
    deadline = monotonic() + timeout_s
    indexed_count = session.scalar(select(func.count(Repository.id))) or 0
    query_count = 4 if indexed_count < 3_000 else 2
    existing = set(session.scalars(select(IndexSyncCursor.query)))
    session.add_all(
        IndexSyncCursor(query=query) for query in REFRESH_QUERIES if query not in existing
    )
    try:
        session.commit()
    except IntegrityError:
        # Another scheduler may initialize the same unique cursors concurrently.
        session.rollback()
    statement = select(IndexSyncCursor).where(IndexSyncCursor.query.in_(REFRESH_QUERIES))
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    selected = _select_refresh_cursors(
        list(session.scalars(statement)), count=query_count, now=utc_now()
    )
    queries = [cursor.query for cursor in selected]
    synchronizer = RepositorySynchronizer(session, client)
    fetched = created = updated = snapshots_created = 0
    failed_queries: list[str] = []
    for index, cursor in enumerate(selected):
        remaining = deadline - monotonic()
        if remaining <= 0:
            failed_queries.extend(queries[index:])
            break
        try:
            with session.begin_nested():
                async with asyncio.timeout(remaining):
                    stats = await synchronizer.sync_query(
                        cursor.query, start_page=cursor.next_page, commit=False
                    )
                cursor.next_page = (
                    1 if cursor.next_page >= 10 or stats.fetched == 0 else cursor.next_page + 1
                )
                cursor.last_success_at = utc_now()
                cursor.failure_count = 0
                cursor.last_error = None
        except (GitHubAPIError, TimeoutError) as exc:
            cursor.failure_count += 1
            cursor.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            failed_queries.append(cursor.query)
            continue
        fetched += stats.fetched
        created += stats.created
        updated += stats.updated
        snapshots_created += stats.snapshots_created
    session.commit()
    return IndexRefreshResponse(
        queries=queries,
        fetched=fetched,
        created=created,
        updated=updated,
        snapshots_created=snapshots_created,
        failed_queries=failed_queries,
        completed_at=utc_now(),
    )


async def run_scheduled_refresh() -> IndexRefreshResponse:
    settings = get_settings()
    factory = create_session_factory(create_db_engine())
    async with GitHubClient(
        token=settings.github_token,
        base_url=settings.github_api_url,
        api_version=settings.github_api_version,
    ) as client:
        with factory() as session:
            return await refresh_index(session, client)


async def run_sync(query: str, pages: int) -> SyncStats:
    settings = get_settings()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    async with GitHubClient(
        token=settings.github_token,
        base_url=settings.github_api_url,
        api_version=settings.github_api_version,
    ) as client:
        with session_factory() as session:
            synchronizer = RepositorySynchronizer(session, client)
            return await synchronizer.sync_query(query, pages=pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize GitHub repositories into GitSeek")
    parser.add_argument("--query", default="language:Python archived:false")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--scheduled", action="store_true", help="refresh one bounded cursor batch")
    args = parser.parse_args()
    if args.scheduled:
        result = asyncio.run(run_scheduled_refresh())
        print(result.model_dump_json())
        raise SystemExit(1 if result.failed_queries else 0)
    stats = asyncio.run(run_sync(args.query, args.pages))
    print(
        f"sync complete: fetched={stats.fetched} "
        f"created={stats.created} updated={stats.updated}"
    )


if __name__ == "__main__":
    main()
