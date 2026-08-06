from fastapi import APIRouter

from packages.domain.feedback import FeedbackReceipt, FeedbackRequest, FeedbackSummary
from packages.feedback import feedback_store

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackReceipt, status_code=201)
async def submit_feedback(request: FeedbackRequest) -> FeedbackReceipt:
    return feedback_store.add(request)


@router.get("/summary", response_model=FeedbackSummary)
async def get_feedback_summary() -> FeedbackSummary:
    return feedback_store.summary()
