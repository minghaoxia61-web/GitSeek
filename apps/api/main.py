from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
        title="OpenScout API",
        description="Evidence-backed GitHub project discovery API",
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(search_router)
    application.include_router(saved_router)
    application.include_router(repositories_router)
    application.include_router(feedback_router)
    application.include_router(evaluations_router)
    return application


app = create_app()
