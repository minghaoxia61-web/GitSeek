import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.dependencies import (
    get_db_session,
    get_embedding_client,
    get_github_client,
    get_query_planner,
)
from packages.agents import AgentWorkflow
from packages.database.session import get_session_factory
from packages.domain.agent import AgentRunRequest, AgentRunResponse, AgentStep
from packages.domain.settings import get_settings
from packages.embeddings import ExternalEmbeddingService, OpenAIEmbeddingClient
from packages.github_client import GitHubAPIError, GitHubClient, GitHubRateLimitError
from packages.model_planning import OpenAIQueryPlanner
from packages.persistence import ProductPersistence
from packages.retrieval import RepositoryIndex

router = APIRouter(prefix="/api/v1/agent", tags=["agent workflow"])
logger = logging.getLogger(__name__)


def _workflow(
    client: GitHubClient,
    session: Session,
    query_planner: OpenAIQueryPlanner | None,
    embedding_client: OpenAIEmbeddingClient | None,
) -> AgentWorkflow:
    return AgentWorkflow(
        client,
        ProductPersistence(session),
        RepositoryIndex(session),
        query_planner,
        (
            ExternalEmbeddingService(session, embedding_client)
            if embedding_client is not None
            else None
        ),
    )


@router.post("/runs", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
    query_planner: Annotated[OpenAIQueryPlanner | None, Depends(get_query_planner)],
    embedding_client: Annotated[
        OpenAIEmbeddingClient | None,
        Depends(get_embedding_client),
    ],
) -> AgentRunResponse:
    try:
        return await _workflow(client, session, query_planner, embedding_client).run(request)
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail={"message": "GitHub rate limit exceeded", "reset_at": exc.reset_at},
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail="Agent retrieval failed") from exc


@router.post("/runs/stream")
async def stream_agent(
    request: AgentRunRequest,
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        async def progress(step: AgentStep) -> None:
            await queue.put(("progress", step.model_dump_json()))

        async def execute() -> None:
            settings = get_settings()
            embedding_client: OpenAIEmbeddingClient | None = None
            try:
                if settings.embedding_api_key is not None and settings.embedding_model:
                    embedding_client = OpenAIEmbeddingClient(
                        settings.embedding_api_key,
                        model=settings.embedding_model,
                        base_url=settings.embedding_api_url,
                    )
                query_planner = (
                    OpenAIQueryPlanner(
                        settings.openai_api_key.get_secret_value(),
                        model=settings.openai_model,
                        base_url=settings.openai_api_url,
                    )
                    if settings.openai_api_key is not None
                    else None
                )
                async with GitHubClient(
                    token=settings.github_token,
                    base_url=settings.github_api_url,
                    api_version=settings.github_api_version,
                ) as client:
                    with get_session_factory()() as session:
                        result = await _workflow(
                            client, session, query_planner, embedding_client
                        ).run(request, progress=progress)
                await queue.put(("result", result.model_dump_json()))
            except GitHubRateLimitError:
                await queue.put(("error", json.dumps({"message": "GitHub rate limit exceeded"})))
            except GitHubAPIError:
                await queue.put(("error", json.dumps({"message": "Agent retrieval failed"})))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Agent stream execution failed")
                await queue.put(("error", json.dumps({"message": "Agent execution failed"})))
            finally:
                if embedding_client is not None:
                    await embedding_client.aclose()

        task = asyncio.create_task(execute())
        try:
            while True:
                event, payload = await queue.get()
                yield f"event: {event}\ndata: {payload}\n\n"
                if event in {"result", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
