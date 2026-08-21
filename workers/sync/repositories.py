import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from packages.database import create_db_engine, create_session_factory
from packages.domain.models import Repository, RepositorySnapshot
from packages.domain.models.base import utc_now
from packages.domain.settings import get_settings
from packages.github_client import GitHubClient
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
    args = parser.parse_args()
    stats = asyncio.run(run_sync(args.query, args.pages))
    print(
        f"sync complete: fetched={stats.fetched} "
        f"created={stats.created} updated={stats.updated}"
    )


if __name__ == "__main__":
    main()
