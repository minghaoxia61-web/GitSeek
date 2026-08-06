from datetime import datetime

from pydantic import BaseModel, Field


class SaveRepositoryRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$", max_length=255)


class SavedRepositoryItem(BaseModel):
    repository: str
    saved_at: datetime | None = None


class SavedRepositoryList(BaseModel):
    device_id: str
    repositories: list[str]
