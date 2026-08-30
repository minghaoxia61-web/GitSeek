"""Repository cloning, workspace paths, and code-chunk ingestion for the fixer agent."""

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from packages.agent_core.chunking import chunk_repository
from packages.domain.models.fixer import AgentCodeChunkRecord


class IngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionStats:
    repo_full_name: str
    chunk_count: int
    embedded_count: int


def workspace_root(root: str | Path | None = None) -> Path:
    base = Path(root) if root else Path(tempfile.gettempdir()) / "gitseek-agent-workspaces"
    base.mkdir(parents=True, exist_ok=True)
    return base


def workspace_for(repo_full_name: str, root: str | Path | None = None) -> Path:
    slug = repo_full_name.strip("/").replace("/", "__")
    path = workspace_root(root) / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def clone_repository(
    clone_url: str,
    dest: Path,
    *,
    depth: int = 1,
    timeout_s: float = 600.0,
) -> Path:
    """Clone a repository into ``dest`` via the git CLI (shallow by default)."""
    if dest.exists() and any(dest.iterdir()):
        raise IngestionError(f"workspace is not empty: {dest}")
    try:
        subprocess.run(
            ["git", "clone", "--depth", str(depth), clone_url, str(dest)],
            check=True,
            capture_output=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as exc:
        raise IngestionError("git CLI is not available on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise IngestionError(f"cloning {clone_url} timed out after {timeout_s}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "ignore")[-300:]
        raise IngestionError(f"git clone failed: {detail}") from exc
    return dest


def _chunk_text_for_embedding(path: str, name: str, summary: str | None, content: str) -> str:
    return f"{path}\n{name}\n{summary or ''}\n{content[:1500]}"


async def ingest_repository(
    session: Session,
    repo_full_name: str,
    repo_root: Path,
    *,
    embedding_client: object | None = None,
    embedding_model: str | None = None,
    batch_size: int = 32,
) -> IngestionStats:
    """Replace the stored code index for one repository with a fresh tree-sitter chunking."""
    chunks = chunk_repository(Path(repo_root))

    session.execute(
        delete(AgentCodeChunkRecord).where(AgentCodeChunkRecord.repo_full_name == repo_full_name)
    )

    vectors: dict[int, list[float]] = {}
    if embedding_client is not None and embedding_model and chunks:
        texts = [_chunk_text_for_embedding(c.path, c.name, c.summary, c.content) for c in chunks]
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            batch_vectors = await embedding_client.embed(batch)  # type: ignore[attr-defined]
            for offset, vector in enumerate(batch_vectors or []):
                vectors[start + offset] = vector

    for index, chunk in enumerate(chunks):
        session.add(
            AgentCodeChunkRecord(
                repo_full_name=repo_full_name,
                path=chunk.path,
                name=chunk.name,
                kind=chunk.kind,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                summary=chunk.summary,
                model=embedding_model if index in vectors else None,
                content_hash=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                vector_json=vectors.get(index),
            )
        )
    session.commit()
    return IngestionStats(
        repo_full_name=repo_full_name,
        chunk_count=len(chunks),
        embedded_count=len(vectors),
    )
