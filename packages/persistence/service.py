from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from packages.domain.agent import AgentRunRequest, AgentRunResponse
from packages.domain.contribution import ContributionIssueResponse
from packages.domain.feedback import FeedbackReceipt, FeedbackRequest, FeedbackSummary
from packages.domain.models import (
    AgentRunRecord,
    AgentStepRecord,
    ContributionIssueRecord,
    FeedbackRecord,
    RecommendationRecord,
    Repository,
    RepositorySnapshot,
    SavedRepository,
    SearchSession,
)
from packages.domain.search import (
    Recommendation,
    RetrievalSummary,
    SearchConstraints,
    SearchRequest,
    SearchResponse,
)
from packages.github_client.schemas import GitHubRepository


def _database_error_code(error: SQLAlchemyError) -> str:
    original = getattr(error, "orig", None)
    diagnostic = getattr(original, "diag", None)
    constraint = getattr(diagnostic, "constraint_name", None)
    sqlstate = getattr(original, "sqlstate", None)
    details = [type(error).__name__]
    if constraint:
        details.append(str(constraint))
    elif sqlstate:
        details.append(str(sqlstate))
    return ":".join(details)


def _repository_values(item: GitHubRepository) -> dict[str, object]:
    return {
        "github_id": item.id,
        "full_name": item.full_name,
        "owner": item.owner.login,
        "name": item.name,
        "description": item.description,
        "html_url": item.html_url,
        "default_branch": item.default_branch,
        "primary_language": item.language,
        "topics": item.topics,
        "license_spdx": item.license.spdx_id if item.license else None,
        "stars": item.stargazers_count,
        "forks": item.forks_count,
        "open_issues": item.open_issues_count,
        "archived": item.archived,
        "pushed_at": item.pushed_at,
        "github_created_at": item.created_at,
        "github_updated_at": item.updated_at,
        "fetched_at": datetime.now(UTC),
        "raw_metadata": item.model_dump(mode="json"),
    }


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class ProductPersistence:
    """Database-backed product activity with graceful degradation when storage is offline."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.last_error: str | None = None

    def save_search(
        self,
        request: SearchRequest,
        response: SearchResponse,
        repositories: list[GitHubRepository],
    ) -> bool:
        self.last_error = None
        try:
            repositories_by_name: dict[str, Repository] = {}
            for item in repositories:
                record = self._session.scalar(
                    select(Repository).where(Repository.github_id == item.id)
                )
                values = _repository_values(item)
                if record is None:
                    record = Repository(**values)
                    self._session.add(record)
                else:
                    for key, value in values.items():
                        setattr(record, key, value)
                repositories_by_name[item.full_name] = record

            self._session.flush()
            for item in repositories:
                record = repositories_by_name[item.full_name]
                self._session.add(
                    RepositorySnapshot(
                        repo_id=record.id,
                        metrics_json={
                            "stars": item.stargazers_count,
                            "forks": item.forks_count,
                            "open_issues": item.open_issues_count,
                            "archived": item.archived,
                            "pushed_at": item.pushed_at.isoformat() if item.pushed_at else None,
                        },
                    )
                )

            self._session.add(
                SearchSession(
                    id=response.session_id,
                    query=request.query,
                    constraints=response.constraints.model_dump(mode="json"),
                    generated_github_query=response.generated_github_query,
                    source_total_count=response.source_total_count,
                    eligible_candidate_count=response.eligible_candidate_count,
                    ranking_version=response.ranking_version,
                )
            )
            self._session.flush()
            for result in response.results:
                self._session.add(
                    RecommendationRecord(
                        session_id=response.session_id,
                        repository_full_name=result.full_name,
                        rank=result.rank,
                        score=result.score,
                        score_json=result.score_breakdown,
                        evidence_json={
                            "constraint_match": result.constraint_match,
                            "reasons": result.reasons,
                            "risks": result.risks,
                            "retrieval_sources": result.retrieval_sources,
                            "data_fetched_at": result.data_fetched_at.isoformat()
                            if result.data_fetched_at
                            else None,
                            "data_valid_until": result.data_valid_until.isoformat()
                            if result.data_valid_until
                            else None,
                        },
                    )
                )
            self._session.commit()
            return True
        except SQLAlchemyError as error:
            self._session.rollback()
            self.last_error = _database_error_code(error)
            return False

    def load_cached_search(
        self,
        query: str,
        constraints: SearchConstraints,
        generated_github_query: str,
        ranking_version: str,
        *,
        limit: int,
        max_age: timedelta = timedelta(minutes=15),
    ) -> SearchResponse | None:
        """Return a recent equivalent search without contacting GitHub again."""
        try:
            normalized_query = " ".join(query.casefold().split())
            cutoff = datetime.now(UTC) - max_age
            candidates = list(
                self._session.scalars(
                    select(SearchSession)
                    .where(SearchSession.created_at >= cutoff)
                    .where(SearchSession.generated_github_query == generated_github_query)
                    .where(SearchSession.ranking_version == ranking_version)
                    .order_by(SearchSession.created_at.desc())
                    .limit(20)
                )
            )
            expected_constraints = constraints.model_dump(mode="json")
            cached_session = next(
                (
                    item
                    for item in candidates
                    if " ".join(item.query.casefold().split()) == normalized_query
                    and item.constraints == expected_constraints
                ),
                None,
            )
            if cached_session is None:
                return None

            rows = self._session.execute(
                select(RecommendationRecord, Repository)
                .join(
                    Repository,
                    Repository.full_name == RecommendationRecord.repository_full_name,
                )
                .where(RecommendationRecord.session_id == cached_session.id)
                .order_by(RecommendationRecord.rank)
                .limit(limit)
            ).all()
            if not rows:
                return None
            if len(rows) < limit and cached_session.eligible_candidate_count > len(rows):
                return None

            recommendations = []
            for recommendation, repository in rows:
                evidence = recommendation.evidence_json or {}
                recommendations.append(
                    Recommendation(
                        rank=recommendation.rank,
                        full_name=repository.full_name,
                        description=repository.description,
                        html_url=repository.html_url,
                        score=recommendation.score,
                        stars=repository.stars,
                        language=repository.primary_language,
                        license_spdx=repository.license_spdx,
                        pushed_at=_as_utc(repository.pushed_at),
                        constraint_match=evidence.get("constraint_match", {}),
                        score_breakdown=recommendation.score_json or {},
                        reasons=evidence.get("reasons", []),
                        risks=evidence.get("risks", []),
                        retrieval_sources=evidence.get("retrieval_sources", []),
                        data_fetched_at=evidence.get("data_fetched_at"),
                        data_valid_until=evidence.get("data_valid_until"),
                    )
                )

            return SearchResponse(
                session_id=cached_session.id,
                query=query,
                generated_github_query=cached_session.generated_github_query,
                constraints=constraints,
                source_total_count=cached_session.source_total_count,
                eligible_candidate_count=cached_session.eligible_candidate_count,
                ranking_version=cached_session.ranking_version,
                results=recommendations,
                retrieval=RetrievalSummary(
                    local_candidates=0,
                    github_candidates=0,
                    github_status="live",
                    cache_hit=True,
                    cached_at=_as_utc(cached_session.created_at),
                ),
            )
        except SQLAlchemyError:
            self._session.rollback()
            return None

    def save_feedback(self, request: FeedbackRequest) -> FeedbackReceipt | None:
        try:
            session_id = request.session_id
            if session_id and self._session.get(SearchSession, session_id) is None:
                session_id = None
            receipt = FeedbackReceipt(
                id=request.id,
                repository=request.repository,
                action=request.action,
                received_at=datetime.now(UTC),
            )
            self._session.add(
                FeedbackRecord(
                    id=receipt.id,
                    session_id=session_id,
                    repository=request.repository,
                    action=request.action,
                    reason=request.reason,
                    query=request.query,
                    device_id=request.device_id,
                    received_at=receipt.received_at,
                )
            )
            self._session.commit()
            return receipt
        except SQLAlchemyError:
            self._session.rollback()
            return None

    def feedback_summary(self) -> FeedbackSummary | None:
        try:
            rows = self._session.execute(
                select(FeedbackRecord.action, func.count(FeedbackRecord.id)).group_by(
                    FeedbackRecord.action
                )
            ).all()
            counts = Counter({action: count for action, count in rows})
            return FeedbackSummary(total=sum(counts.values()), by_action=dict(counts))
        except SQLAlchemyError:
            self._session.rollback()
            return None

    def save_repository(self, device_id: str, repository: str) -> list[str] | None:
        try:
            existing = self._session.scalar(
                select(SavedRepository).where(
                    SavedRepository.device_id == device_id,
                    SavedRepository.repository == repository,
                )
            )
            if existing is None:
                self._session.add(SavedRepository(device_id=device_id, repository=repository))
                self._session.commit()
            return self.list_saved_repositories(device_id)
        except SQLAlchemyError:
            self._session.rollback()
            return None

    def list_saved_repositories(self, device_id: str) -> list[str] | None:
        try:
            return list(
                self._session.scalars(
                    select(SavedRepository.repository)
                    .where(SavedRepository.device_id == device_id)
                    .order_by(SavedRepository.created_at.desc())
                )
            )
        except SQLAlchemyError:
            self._session.rollback()
            return None

    def delete_saved_repository(self, device_id: str, repository: str) -> list[str] | None:
        try:
            self._session.execute(
                delete(SavedRepository).where(
                    SavedRepository.device_id == device_id,
                    SavedRepository.repository == repository,
                )
            )
            self._session.commit()
            return self.list_saved_repositories(device_id)
        except SQLAlchemyError:
            self._session.rollback()
            return None

    def save_issues(self, response: ContributionIssueResponse) -> bool:
        try:
            fetched_at = response.fetched_at
            for issue in response.issues:
                record = self._session.scalar(
                    select(ContributionIssueRecord).where(
                        ContributionIssueRecord.repository_full_name == response.full_name,
                        ContributionIssueRecord.issue_number == issue.number,
                    )
                )
                values = {
                    "title": issue.title,
                    "html_url": issue.html_url,
                    "state": "open",
                    "labels": issue.labels,
                    "assigned": False,
                    "comments": issue.comments,
                    "difficulty": issue.difficulty,
                    "score": issue.score,
                    "updated_at": issue.updated_at,
                    "fetched_at": fetched_at,
                }
                if record is None:
                    self._session.add(
                        ContributionIssueRecord(
                            repository_full_name=response.full_name,
                            issue_number=issue.number,
                            **values,
                        )
                    )
                else:
                    for key, value in values.items():
                        setattr(record, key, value)
            self._session.commit()
            return True
        except SQLAlchemyError:
            self._session.rollback()
            return False

    def save_agent_run(
        self,
        request: AgentRunRequest,
        response: AgentRunResponse,
    ) -> bool:
        try:
            search_session_id = response.search.session_id
            if self._session.get(SearchSession, search_session_id) is None:
                search_session_id = None
            self._session.add(
                AgentRunRecord(
                    id=response.run_id,
                    search_session_id=search_session_id,
                    status=response.status,
                    request_json=request.model_dump(mode="json"),
                    result_json={
                        "interpretation": response.interpretation.model_dump(mode="json"),
                        "search_plan": response.search_plan,
                        "verification": [
                            item.model_dump(mode="json") for item in response.verification
                        ],
                        "investigated_repositories": [
                            item.full_name for item in response.investigations
                        ],
                    },
                    retry_count=response.retry_count,
                    created_at=response.created_at,
                    completed_at=response.completed_at,
                )
            )
            for step in response.steps:
                self._session.add(
                    AgentStepRecord(
                        run_id=response.run_id,
                        node=step.node,
                        status=step.status,
                        duration_ms=step.duration_ms,
                        attempts=step.attempts,
                        summary=step.summary,
                        started_at=step.started_at,
                        completed_at=step.completed_at,
                    )
                )
            self._session.commit()
            return True
        except SQLAlchemyError:
            self._session.rollback()
            return False
