"""Issue-to-PR repair agent core: locator, minimal fixer loop, and LLM plumbing."""

from packages.agent_core.chunking import CodeChunk, chunk_python_source, chunk_repository
from packages.agent_core.fixer import (
    FAILURE_CATEGORIES,
    FixerAgent,
    FixerConfig,
    FixerResult,
    FixerStepTrace,
)
from packages.agent_core.ingestion import (
    IngestionError,
    IngestionStats,
    clone_repository,
    ingest_repository,
    workspace_for,
)
from packages.agent_core.issue_parser import IssueAnalysis, parse_issue
from packages.agent_core.llm import AgentLLMError, ChatCompletionClient, ChatResult
from packages.agent_core.locator import LocatorCandidate, locate

__all__ = [
    "AgentLLMError",
    "ChatCompletionClient",
    "ChatResult",
    "CodeChunk",
    "FAILURE_CATEGORIES",
    "FixerAgent",
    "FixerConfig",
    "FixerResult",
    "FixerStepTrace",
    "IngestionError",
    "IngestionStats",
    "IssueAnalysis",
    "LocatorCandidate",
    "chunk_python_source",
    "chunk_repository",
    "clone_repository",
    "ingest_repository",
    "locate",
    "parse_issue",
    "workspace_for",
]
