from typing import Annotated

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_embedding_client
from packages.domain.evaluation import EmbeddingEvaluationSummary, EvaluationSummary
from packages.embeddings import OpenAIEmbeddingClient
from packages.evaluation import build_evaluation_summary, evaluate_external_embeddings

router = APIRouter(prefix="/api/v1/evals", tags=["evaluations"])


@router.get("/summary", response_model=EvaluationSummary)
async def get_evaluation_summary() -> EvaluationSummary:
    return build_evaluation_summary()


@router.post("/run", response_model=EvaluationSummary)
async def run_evaluation() -> EvaluationSummary:
    return build_evaluation_summary()


@router.post("/embeddings", response_model=EmbeddingEvaluationSummary)
async def run_embedding_evaluation(
    client: Annotated[OpenAIEmbeddingClient | None, Depends(get_embedding_client)],
) -> EmbeddingEvaluationSummary:
    return await evaluate_external_embeddings(client)
