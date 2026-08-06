from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FeedbackAction = Literal["helpful", "not_relevant", "saved", "opened_issue"]


class FeedbackRequest(BaseModel):
    repository: str
    action: FeedbackAction
    reason: str | None = Field(default=None, max_length=240)
    query: str | None = Field(default=None, max_length=500)


class FeedbackReceipt(BaseModel):
    id: str
    repository: str
    action: FeedbackAction
    received_at: datetime


class FeedbackSummary(BaseModel):
    total: int
    by_action: dict[str, int]
