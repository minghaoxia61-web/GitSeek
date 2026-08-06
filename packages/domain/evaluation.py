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
    case: str
    expected: str
    actual: str


class EvaluationSummary(BaseModel):
    version: str
    dataset_version: str
    sample_count: int
    generated_at: datetime
    metrics: list[EvaluationMetric]
    failures: list[EvaluationFailure] = Field(default_factory=list)
