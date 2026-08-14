from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RepositoryIndexStatus(BaseModel):
    repository_count: int
    snapshot_count: int
    freshest_at: datetime | None
    oldest_at: datetime | None = None
    stale_repository_count: int = 0
    expired_repository_count: int = 0
    freshness_state: Literal["empty", "fresh", "stale", "expired"] = "empty"
    next_refresh_at: datetime | None = None
    ready: bool
    storage_status: Literal["ready", "unavailable"] = "ready"


class IndexRefreshResponse(BaseModel):
    queries: list[str]
    fetched: int
    created: int
    updated: int
    snapshots_created: int = 0
    pruned: int = 0
    failed_queries: list[str] = []
    completed_at: datetime
