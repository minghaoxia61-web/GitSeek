from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session
from packages.domain.feedback import FeedbackReceipt, FeedbackRequest, FeedbackSummary
from packages.feedback import feedback_store
from packages.persistence import ProductPersistence

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackReceipt, status_code=201)
async def submit_feedback(
    request: FeedbackRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> FeedbackReceipt:
    return ProductPersistence(session).save_feedback(request) or feedback_store.add(request)


@router.get("/summary", response_model=FeedbackSummary)
async def get_feedback_summary(
    session: Annotated[Session, Depends(get_db_session)],
) -> FeedbackSummary:
    return ProductPersistence(session).feedback_summary() or feedback_store.summary()
