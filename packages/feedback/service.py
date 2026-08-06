from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from packages.domain.feedback import FeedbackReceipt, FeedbackRequest, FeedbackSummary


class FeedbackStore:
    def __init__(self) -> None:
        self._items: list[FeedbackReceipt] = []

    def add(self, request: FeedbackRequest) -> FeedbackReceipt:
        receipt = FeedbackReceipt(
            id=str(uuid4()),
            repository=request.repository,
            action=request.action,
            received_at=datetime.now(UTC),
        )
        self._items.append(receipt)
        return receipt

    def summary(self) -> FeedbackSummary:
        counts = Counter(item.action for item in self._items)
        return FeedbackSummary(total=len(self._items), by_action=dict(counts))

    def clear(self) -> None:
        self._items.clear()


feedback_store = FeedbackStore()
