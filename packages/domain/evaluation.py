from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EvaluationMetric(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    target: float
    passed: bool


class EvaluationFailure(BaseModel):
    case_id: str
    category: str
    case: str
    expected: str
    actual: str


class EvaluationCategory(BaseModel):
    key: str
    label: str
    passed_fields: int
    total_fields: int
    accuracy: float


class EvaluationExperiment(BaseModel):
    key: str
    label: str
    recall_at_10: float
    ndcg_at_10: float
    mrr_at_10: float


class RetrievalChannelExperiment(EvaluationExperiment):
    query_count: int
    coverage: float


class RetrievalDiagnostic(BaseModel):
    query_id: str
    query: str
    category: str
    severity: Literal["high", "medium", "low"]
    summary: str
    expected_repositories: list[str] = Field(default_factory=list)
    missing_repositories: list[str] = Field(default_factory=list)
    evidence: dict[str, float] = Field(default_factory=dict)
    suggestion: str


class EvaluationSummary(BaseModel):
    version: str
    dataset_version: str
    sample_count: int
    generated_at: datetime
    retrieval_dataset_version: str | None = None
    retrieval_case_count: int = 0
    relevance_judgment_count: int = 0
    preference_dataset_version: str | None = None
    preference_pair_count: int = 0
    retrieval_snapshot_id: str | None = None
    channel_experiments: list[RetrievalChannelExperiment] = Field(default_factory=list)
    retrieval_diagnostics: list[RetrievalDiagnostic] = Field(default_factory=list)
    metrics: list[EvaluationMetric]
    experiments: list[EvaluationExperiment] = Field(default_factory=list)
    categories: list[EvaluationCategory] = Field(default_factory=list)
    failures: list[EvaluationFailure] = Field(default_factory=list)


class EmbeddingEvaluationSummary(BaseModel):
    configured: bool
    status: Literal["completed", "unavailable", "failed"]
    model: str | None = None
    sample_count: int = 0
    metrics: list[EvaluationMetric] = Field(default_factory=list)
