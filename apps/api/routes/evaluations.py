from fastapi import APIRouter

from packages.domain.evaluation import EvaluationSummary
from packages.evaluation import build_evaluation_summary

router = APIRouter(prefix="/api/v1/evals", tags=["evaluations"])


@router.get("/summary", response_model=EvaluationSummary)
async def get_evaluation_summary() -> EvaluationSummary:
    return build_evaluation_summary()


@router.post("/run", response_model=EvaluationSummary)
async def run_evaluation() -> EvaluationSummary:
    return build_evaluation_summary()
