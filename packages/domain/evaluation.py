from datetime import datetime

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


class EvaluationSummary(BaseModel):
    version: str
    dataset_version: str
    sample_count: int
    generated_at: datetime
    metrics: list[EvaluationMetric]
    categories: list[EvaluationCategory] = Field(default_factory=list)
    failures: list[EvaluationFailure] = Field(default_factory=list)
