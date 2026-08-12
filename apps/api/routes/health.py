from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.observability import runtime_metrics
from packages.domain.settings import get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    embedding_configured: bool = False
    embedding_model: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        embedding_configured=bool(settings.embedding_api_key and settings.embedding_model),
        embedding_model=settings.embedding_model,
    )


@router.get("/api/v1/metrics")
async def metrics() -> dict:
    return runtime_metrics.snapshot()
