import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from apps.api.observability import PublicRateLimitMiddleware, RequestObservabilityMiddleware
from apps.api.routes.agents import router as agents_router
from apps.api.routes.evaluations import router as evaluations_router
from apps.api.routes.feedback import router as feedback_router
from apps.api.routes.fixer import router as fixer_router
from apps.api.routes.health import router as health_router
from apps.api.routes.jobs import router as jobs_router
from apps.api.routes.repositories import router as repositories_router
from apps.api.routes.saved import router as saved_router
from apps.api.routes.search import router as search_router
from packages.domain.settings import get_settings

logger = logging.getLogger("gitseek.app")


async def database_unavailable_handler(_: Request, exc: Exception) -> JSONResponse:
    """Return a CORS-visible 503 instead of a bare 500 (which browsers report as network errors)."""
    logger.error("database unavailable: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "数据库暂时不可用，请稍后再试；若持续出现请检查数据库连接配置。"},
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="GitSeek API",
        description="Evidence-backed GitHub project discovery API",
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_origin_regex=r"https://(?:([a-z0-9-]+\.)*chatgpt\.site|minghaoxia61-web\.github\.io)",
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    application.add_middleware(RequestObservabilityMiddleware)
    application.add_middleware(
        PublicRateLimitMiddleware,
        search_limit=settings.public_rate_limit_per_minute,
        agent_limit=settings.agent_rate_limit_per_minute,
    )
    application.include_router(health_router)
    application.include_router(jobs_router)
    application.include_router(agents_router)
    application.include_router(fixer_router)
    application.add_exception_handler(SQLAlchemyError, database_unavailable_handler)
    application.include_router(search_router)
    application.include_router(saved_router)
    application.include_router(repositories_router)
    application.include_router(feedback_router)
    application.include_router(evaluations_router)
    return application


app = create_app()
