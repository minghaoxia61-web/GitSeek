from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from packages.domain.investigation import RepositoryInvestigation
from packages.domain.query_plan import QueryInterpretation
from packages.domain.search import SearchRequest, SearchResponse

AgentNode = Literal[
    "parse_query",
    "plan_search",
    "retrieve_candidates",
    "investigate_repositories",
    "verify_evidence",
]
AgentStepStatus = Literal["completed", "partial", "failed"]


class AgentRunRequest(SearchRequest):
    investigate_limit: int = Field(default=0, ge=0, le=3)


class AgentStep(BaseModel):
    node: AgentNode
    status: AgentStepStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    attempts: int = Field(default=1, ge=1, le=2)
    summary: str


class EvidenceVerification(BaseModel):
    full_name: str
    checked_claims: int
    supported_claims: int
    conflicts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    support_ratio: float = Field(ge=0, le=1)
    confidence: Literal["high", "medium", "low"]


class AgentRunResponse(BaseModel):
    run_id: str
    status: Literal["succeeded", "partial", "failed"]
    created_at: datetime
    completed_at: datetime
    retry_count: int = Field(default=0, ge=0, le=1)
    interpretation: QueryInterpretation
    search_plan: list[str]
    search: SearchResponse
    investigations: list[RepositoryInvestigation]
    verification: list[EvidenceVerification]
    steps: list[AgentStep]
