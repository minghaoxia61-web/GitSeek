import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, cast, func, literal_column, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from packages.domain.index import RepositoryIndexStatus
from packages.domain.models import Repository, RepositorySnapshot
from packages.domain.search import SearchConstraints
from packages.github_client.schemas import GitHubRepository

IGNORED_QUERY_TERMS = {
    "github",
    "issue",
    "mit",
    "python",
    "windows",
}


@dataclass(frozen=True)
class IndexedRepository:
    repository: GitHubRepository
    fetched_at: datetime


class RepositoryIndex:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        query: str,
        constraints: SearchConstraints,
        *,
        limit: int = 200,
    ) -> list[IndexedRepository]:
        statement = select(Repository)
        statement = statement.where(
            or_(
                Repository.primary_language.is_(None),
                func.lower(Repository.primary_language) == constraints.language.casefold(),
            )
        )
        if constraints.exclude_archived:
            statement = statement.where(Repository.archived.is_(False))
        if constraints.licenses:
            statement = statement.where(Repository.license_spdx.in_(constraints.licenses))
        if constraints.pushed_after:
            statement = statement.where(Repository.pushed_at > constraints.pushed_after)
        if constraints.project_size == "small":
            statement = statement.where(Repository.stars < 5_000)
        elif constraints.project_size == "medium":
            statement = statement.where(Repository.stars.between(1_000, 30_000))
        elif constraints.project_size == "large":
            statement = statement.where(Repository.stars > 10_000)

        terms = list(constraints.technologies)
        if not terms:
            terms = [
                item
                for item in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}", query)
                if item.casefold() not in IGNORED_QUERY_TERMS
            ][:4]
        if terms:
            if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
                search_document = literal_column("search_document")
                search_query = func.websearch_to_tsquery(
                    literal_column("'simple'::regconfig"),
                    " OR ".join(terms),
                )
                statement = statement.where(search_document.op("@@")(search_query))
                statement = statement.order_by(func.ts_rank(search_document, search_query).desc())
            else:
                corpus_columns = (
                    Repository.name,
                    Repository.description,
                    cast(Repository.topics, String),
                )
                statement = statement.where(
                    or_(
                        *[
                            column.ilike(f"%{term}%")
                            for term in terms
                            for column in corpus_columns
                        ]
                    )
                )

        statement = statement.order_by(
            Repository.pushed_at.desc().nullslast(),
            Repository.stars.desc(),
        ).limit(max(1, min(limit, 500)))
        try:
            records = list(self._session.scalars(statement))
        except SQLAlchemyError:
            self._session.rollback()
            return []
        return [
            IndexedRepository(repository=self._to_github(record), fetched_at=record.fetched_at)
            for record in records
        ]

    def status(self) -> RepositoryIndexStatus:
        try:
            repository_count = self._session.scalar(select(func.count(Repository.id))) or 0
            snapshot_count = self._session.scalar(
                select(func.count(RepositorySnapshot.id))
            ) or 0
            freshest_at = self._session.scalar(select(func.max(Repository.fetched_at)))
            return RepositoryIndexStatus(
                repository_count=repository_count,
                snapshot_count=snapshot_count,
                freshest_at=freshest_at,
                ready=repository_count > 0,
            )
        except SQLAlchemyError:
            self._session.rollback()
            return RepositoryIndexStatus(
                repository_count=0,
                snapshot_count=0,
                freshest_at=None,
                ready=False,
            )

    @staticmethod
    def _to_github(record: Repository) -> GitHubRepository:
        return GitHubRepository.model_validate(
            {
                "id": record.github_id,
                "name": record.name,
                "full_name": record.full_name,
                "owner": {"login": record.owner},
                "description": record.description,
                "html_url": record.html_url,
                "default_branch": record.default_branch,
                "language": record.primary_language,
                "topics": record.topics,
                "license": {"spdx_id": record.license_spdx}
                if record.license_spdx
                else None,
                "stargazers_count": record.stars,
                "forks_count": record.forks,
                "open_issues_count": record.open_issues,
                "archived": record.archived,
                "pushed_at": record.pushed_at,
                "created_at": record.github_created_at,
                "updated_at": record.github_updated_at,
            }
        )
