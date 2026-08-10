from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes.agents import router as agents_router
from apps.api.routes.evaluations import router as evaluations_router
from apps.api.routes.feedback import router as feedback_router
from apps.api.routes.health import router as health_router
from apps.api.routes.repositories import router as repositories_router
from apps.api.routes.saved import router as saved_router
from apps.api.routes.search import router as search_router
from packages.domain.settings import get_settings


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
        allow_origin_regex=r"https://([a-z0-9-]+\.)*chatgpt\.site",
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    application.include_router(health_router)
    application.include_router(agents_router)
    application.include_router(search_router)
    application.include_router(saved_router)
    application.include_router(repositories_router)
    application.include_router(feedback_router)
    application.include_router(evaluations_router)
    return application


app = create_app()
