import asyncio
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from packages.domain.agent import (
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    EvidenceVerification,
)
from packages.domain.investigation import RepositoryInvestigation
from packages.domain.query_plan import QueryInterpretation
from packages.github_client import GitHubAPIError, GitHubClient, GitHubRateLimitError
from packages.investigation import RepositoryInvestigator
from packages.model_planning import ModelPlanningError, OpenAIQueryPlanner
from packages.persistence import ProductPersistence
from packages.retrieval import RepositoryIndex, build_github_query, parse_search_constraints
from packages.search import SearchService


def _step(
    node: str,
    started_at: datetime,
    started_clock: float,
    summary: str,
    *,
    status: str = "completed",
    attempts: int = 1,
) -> AgentStep:
    completed_at = datetime.now(UTC)
    return AgentStep(
        node=node,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=max(0, round((perf_counter() - started_clock) * 1000)),
        attempts=attempts,
        summary=summary,
    )


def _verify(
    full_name: str,
    reasons: list[str],
    constraint_match: dict[str, str],
    investigation: RepositoryInvestigation | None,
) -> EvidenceVerification:
    conflicts = [key for key, value in constraint_match.items() if value != "MATCH"]
    checked = len(reasons) + len(constraint_match)
    supported = len(reasons) + sum(value == "MATCH" for value in constraint_match.values())
    evidence_ids: list[str] = []
    if investigation is not None:
        checked += len(investigation.evidence)
        supported_evidence = [item for item in investigation.evidence if item.source_url]
        supported += len(supported_evidence)
        evidence_ids = [item.id for item in supported_evidence]
        if investigation.full_name != full_name:
            conflicts.append("repository_identity")
    if checked == 0:
        ratio = 0.0
    else:
        ratio = round(supported / checked, 3)
    if conflicts or ratio < 0.7:
        confidence = "low"
    elif ratio < 0.9 or investigation is None or investigation.confidence == "low":
        confidence = "medium"
    else:
        confidence = "high"
    return EvidenceVerification(
        full_name=full_name,
        checked_claims=checked,
        supported_claims=supported,
        conflicts=conflicts,
        evidence_ids=evidence_ids,
        support_ratio=ratio,
        confidence=confidence,
    )


class AgentWorkflow:
    def __init__(
        self,
        client: GitHubClient,
        persistence: ProductPersistence | None = None,
        repository_index: RepositoryIndex | None = None,
        query_planner: OpenAIQueryPlanner | None = None,
    ) -> None:
        self._client = client
        self._persistence = persistence
        self._repository_index = repository_index
        self._query_planner = query_planner

    async def run(self, request: AgentRunRequest) -> AgentRunResponse:
        run_id = str(uuid4())
        created_at = datetime.now(UTC)
        steps: list[AgentStep] = []

        started_at, started_clock = datetime.now(UTC), perf_counter()
        constraints = parse_search_constraints(request.query)
        search_terms = list(constraints.technologies)
        interpretation = QueryInterpretation(
            source="rules",
            summary="使用内置规则识别查询条件",
            search_terms=search_terms,
            fallback_reason="OPENAI_API_KEY 未配置",
        )
        if self._query_planner is not None:
            try:
                model_plan = await self._query_planner.plan(request.query)
                constraints = model_plan.constraints()
                search_terms = model_plan.github_terms or model_plan.technologies
                interpretation = QueryInterpretation(
                    source="model",
                    model=self._query_planner.model,
                    summary=model_plan.summary,
                    search_terms=search_terms,
                )
            except ModelPlanningError:
                interpretation = QueryInterpretation(
                    source="rules",
                    model=self._query_planner.model,
                    summary="模型解析暂时不可用，已使用内置规则",
                    search_terms=search_terms,
                    fallback_reason="模型请求失败或输出无效",
                )
        if request.purpose is not None:
            constraints.purpose = request.purpose
        if request.weekly_hours is not None:
            constraints.weekly_hours = request.weekly_hours
        if request.platform:
            constraints.platform = request.platform
        if request.project_size:
            constraints.project_size = request.project_size
        if request.licenses is not None:
            constraints.licenses = request.licenses
        if request.pushed_after is not None:
            constraints.pushed_after = request.pushed_after
        steps.append(
            _step(
                "parse_query",
                started_at,
                started_clock,
                (
                    f"{interpretation.model} 已理解需求：{interpretation.summary}"
                    if interpretation.source == "model"
                    else f"规则解析：{interpretation.summary}"
                ),
                status="completed" if interpretation.source == "model" else "partial",
            )
        )

        started_at, started_clock = datetime.now(UTC), perf_counter()
        github_query = build_github_query(constraints, search_terms)
        search_plan = [
            f"local-index:{request.query}",
            f"github-live:{github_query}",
            f"investigate-top:{request.investigate_limit}",
        ]
        steps.append(
            _step(
                "plan_search",
                started_at,
                started_clock,
                "规划本地索引与 GitHub 实时双路召回，并限制深度调查数量",
            )
        )

        started_at, started_clock = datetime.now(UTC), perf_counter()
        search = await SearchService(
            self._client,
            self._persistence,
            self._repository_index,
        ).search(request, constraints=constraints, search_terms=search_terms)
        steps.append(
            _step(
                "retrieve_candidates",
                started_at,
                started_clock,
                f"合并后得到 {search.eligible_candidate_count} 个合格候选，"
                f"返回 Top {len(search.results)}",
                status=(
                    "partial"
                    if search.retrieval.github_status == "unavailable"
                    else "completed"
                ),
            )
        )

        started_at, started_clock = datetime.now(UTC), perf_counter()
        selected = search.results[: request.investigate_limit]
        investigation_results = await asyncio.gather(
            *[self._investigate(item.full_name) for item in selected]
        )
        investigations = [item[0] for item in investigation_results if item[0] is not None]
        max_attempts = max((item[1] for item in investigation_results), default=1)
        failed_count = sum(item[0] is None for item in investigation_results)
        steps.append(
            _step(
                "investigate_repositories",
                started_at,
                started_clock,
                f"完成 {len(investigations)}/{len(selected)} 个仓库的只读证据调查",
                status="partial" if failed_count else "completed",
                attempts=max_attempts,
            )
        )

        started_at, started_clock = datetime.now(UTC), perf_counter()
        investigation_map = {item.full_name: item for item in investigations}
        verification = [
            _verify(
                item.full_name,
                item.reasons,
                item.constraint_match,
                investigation_map.get(item.full_name),
            )
            for item in selected
        ]
        conflicts = sum(bool(item.conflicts) for item in verification)
        steps.append(
            _step(
                "verify_evidence",
                started_at,
                started_clock,
                f"验证 {len(verification)} 个推荐，发现 {conflicts} 个事实冲突",
                status="partial" if failed_count or conflicts else "completed",
            )
        )

        status = (
            "partial"
            if failed_count or conflicts or interpretation.source == "rules"
            else "succeeded"
        )
        response = AgentRunResponse(
            run_id=run_id,
            status=status,
            created_at=created_at,
            completed_at=datetime.now(UTC),
            retry_count=1 if max_attempts > 1 else 0,
            interpretation=interpretation,
            search_plan=search_plan,
            search=search,
            investigations=investigations,
            verification=verification,
            steps=steps,
        )
        if self._persistence is not None:
            self._persistence.save_agent_run(request, response)
        return response

    async def _investigate(
        self,
        full_name: str,
    ) -> tuple[RepositoryInvestigation | None, int]:
        owner, repo = full_name.split("/", 1)
        investigator = RepositoryInvestigator(self._client)
        for attempt in (1, 2):
            try:
                return await investigator.investigate(owner, repo), attempt
            except GitHubRateLimitError:
                return None, attempt
            except GitHubAPIError:
                if attempt == 2:
                    return None, attempt
        return None, 2
