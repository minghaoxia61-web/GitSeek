"""Hybrid code locator: BM25-style FTS + optional vector channel, fused with RRF.

Reuses :func:`packages.ranking.reciprocal_rank_fusion` so the locator inherits the same
fusion behaviour as repository retrieval. The PostgreSQL FTS branch relies on the
``search_document`` generated column created by migration 20260830_0009; SQLite (tests)
degrades to ``ilike`` matching.
"""

import math
from dataclasses import dataclass

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import Session

from packages.domain.models.fixer import AgentCodeChunkRecord
from packages.ranking import reciprocal_rank_fusion

RRF_RANK_CONSTANT = 60
SNIPPET_CHARS = 400


@dataclass(frozen=True)
class LocatorCandidate:
    chunk_id: int
    path: str
    name: str
    kind: str
    start_line: int
    end_line: int
    score: float
    channels: tuple[str, ...]
    snippet: str


def _sanitize_terms(terms: list[str], limit: int = 12) -> list[str]:
    cleaned: list[str] = []
    for term in terms:
        safe = "".join(ch if (ch.isalnum() or ch in "_.-") else " " for ch in term).strip()
        if len(safe) >= 2 and safe not in cleaned:
            cleaned.append(safe)
    return cleaned[:limit]


def keyword_channel(
    session: Session,
    repo_full_name: str,
    terms: list[str],
    *,
    limit: int = 200,
) -> list[int]:
    if not terms:
        return []
    cleaned = _sanitize_terms(terms)
    if not cleaned:
        return []

    base = select(AgentCodeChunkRecord).where(AgentCodeChunkRecord.repo_full_name == repo_full_name)
    if session.get_bind().dialect.name == "postgresql":
        query_text = " OR ".join(cleaned)
        tsquery = func.websearch_to_tsquery(literal_column("'simple'::regconfig"), query_text)
        try:
            rows = session.execute(
                base.where(literal_column("search_document").op("@@")(tsquery))
                .order_by(func.ts_rank(literal_column("search_document"), tsquery).desc())
                .limit(limit)
            ).scalars().all()
            return [row.id for row in rows]
        except Exception:  # noqa: BLE001 - missing generated column: degrade to ilike
            session.rollback()

    predicates = [
        AgentCodeChunkRecord.content.ilike(f"%{term}%")
        | AgentCodeChunkRecord.path.ilike(f"%{term}%")
        | AgentCodeChunkRecord.name.ilike(f"%{term}%")
        for term in cleaned
    ]
    rows = session.execute(base.where(or_(*predicates)).limit(limit)).scalars().all()
    return [row.id for row in rows]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


async def semantic_channel(
    session: Session,
    repo_full_name: str,
    query_text: str,
    *,
    embedding_client: object | None,
    embedding_model: str | None,
    limit: int = 200,
) -> list[int]:
    if embedding_client is None or not embedding_model or not query_text.strip():
        return []
    rows = session.execute(
        select(AgentCodeChunkRecord.id, AgentCodeChunkRecord.vector_json)
        .where(AgentCodeChunkRecord.repo_full_name == repo_full_name)
        .where(AgentCodeChunkRecord.model == embedding_model)
        .where(AgentCodeChunkRecord.vector_json.is_not(None))
    ).all()
    if not rows:
        return []
    vectors = await embedding_client.embed([query_text[:2000]])  # type: ignore[attr-defined]
    if not vectors:
        return []
    query_vector = vectors[0]
    scored = [
        (row_id, _cosine_similarity(query_vector, vector))
        for row_id, vector in rows
        if vector
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [row_id for row_id, _ in scored[:limit]]


async def locate(
    session: Session,
    repo_full_name: str,
    issue_text: str,
    *,
    search_terms: list[str],
    embedding_client: object | None = None,
    embedding_model: str | None = None,
    top_k: int = 10,
) -> list[LocatorCandidate]:
    """Rank code chunks for an issue; keyword evidence always runs, vectors when configured."""
    channels: dict[str, list[str]] = {}
    keyword_ids = keyword_channel(session, repo_full_name, search_terms)
    if keyword_ids:
        channels["keyword"] = [str(chunk_id) for chunk_id in keyword_ids]
    semantic_ids = await semantic_channel(
        session,
        repo_full_name,
        issue_text[:2000],
        embedding_client=embedding_client,
        embedding_model=embedding_model,
    )
    if semantic_ids:
        channels["semantic"] = [str(chunk_id) for chunk_id in semantic_ids]
    if not channels:
        return []

    fusion = reciprocal_rank_fusion(channels, rank_constant=RRF_RANK_CONSTANT)
    ordered = sorted(fusion.scores.items(), key=lambda item: item[1], reverse=True)
    id_to_channels: dict[str, tuple[str, ...]] = {
        chunk_id: tuple(sorted(name for name, ids in channels.items() if chunk_id in ids))
        for chunk_id in fusion.scores
    }

    top_ids = [int(chunk_id) for chunk_id, _ in ordered[: top_k * 3]]
    rows = session.execute(
        select(AgentCodeChunkRecord).where(AgentCodeChunkRecord.id.in_(top_ids))
    ).scalars().all()
    row_by_id = {row.id: row for row in rows}

    candidates: list[LocatorCandidate] = []
    for chunk_id, score in ordered:
        if len(candidates) >= top_k:
            break
        row = row_by_id.get(int(chunk_id))
        if row is None:
            continue
        candidates.append(
            LocatorCandidate(
                chunk_id=row.id,
                path=row.path,
                name=row.name,
                kind=row.kind,
                start_line=row.start_line,
                end_line=row.end_line,
                score=round(score, 6),
                channels=id_to_channels.get(chunk_id, ()),
                snippet=(row.content or "")[:SNIPPET_CHARS],
            )
        )
    return candidates
