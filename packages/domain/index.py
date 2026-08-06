from datetime import datetime

from pydantic import BaseModel


class RepositoryIndexStatus(BaseModel):
    repository_count: int
    snapshot_count: int
    freshest_at: datetime | None
    ready: bool
