from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db_session, get_github_client, get_query_planner
from packages.agents import AgentWorkflow
from packages.domain.agent import AgentRunRequest, AgentRunResponse
from packages.github_client import GitHubAPIError, GitHubClient, GitHubRateLimitError
from packages.model_planning import OpenAIQueryPlanner
from packages.persistence import ProductPersistence
from packages.retrieval import RepositoryIndex

router = APIRouter(prefix="/api/v1/agent", tags=["agent workflow"])


@router.post("/runs", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    client: Annotated[GitHubClient, Depends(get_github_client)],
    session: Annotated[Session, Depends(get_db_session)],
    query_planner: Annotated[OpenAIQueryPlanner | None, Depends(get_query_planner)],
) -> AgentRunResponse:
    try:
        return await AgentWorkflow(
            client,
            ProductPersistence(session),
            RepositoryIndex(session),
            query_planner,
        ).run(request)
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail={"message": "GitHub rate limit exceeded", "reset_at": exc.reset_at},
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(status_code=502, detail="Agent retrieval failed") from exc
