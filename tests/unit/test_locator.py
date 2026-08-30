import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from packages.agent_core.locator import keyword_channel, locate
from packages.domain.models import Base
from packages.domain.models.fixer import AgentCodeChunkRecord


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def seed_chunks(session, repo: str = "owner/repo") -> None:  # noqa: ANN001 - Session
    rows = [
        ("auth_service.py", "login_user", "def login_user(token):\n    return token\n"),
        ("billing.py", "charge_card", "def charge_card(amount):\n    return amount\n"),
        ("utils/misc.py", "slugify", "def slugify(value):\n    return value\n"),
    ]
    for path, name, content in rows:
        session.add(
            AgentCodeChunkRecord(
                repo_full_name=repo,
                path=path,
                name=name,
                kind="function",
                start_line=1,
                end_line=2,
                content=content,
                summary=content.splitlines()[0],
            )
        )
    session.commit()


def test_keyword_channel_matches_content_and_names():
    session = make_session()
    seed_chunks(session)
    ids = keyword_channel(session, "owner/repo", ["login_user", "charge_card"])
    assert len(ids) == 2
    assert keyword_channel(session, "owner/repo", []) == []


def test_locate_returns_candidates_with_keyword_evidence():
    session = make_session()
    seed_chunks(session)
    results = asyncio.run(
        locate(
            session,
            "owner/repo",
            "login_user fails on expired token",
            search_terms=["login_user"],
            top_k=5,
        )
    )
    assert results, "expected at least one locator candidate"
    top = results[0]
    assert top.channels == ("keyword",)
    assert top.score > 0
    assert top.name == "login_user"
    assert top.snippet


def test_locate_returns_empty_without_matches():
    session = make_session()
    seed_chunks(session)
    results = asyncio.run(
        locate(session, "owner/repo", "unrelated", search_terms=["nonexistent_term"])
    )
    assert results == []


def test_locate_respects_top_k():
    session = make_session()
    seed_chunks(session)
    results = asyncio.run(
        locate(
            session,
            "owner/repo",
            "token amount value",
            search_terms=["token", "amount", "value"],
            top_k=1,
        )
    )
    assert len(results) <= 1


@pytest.mark.parametrize("term", ["`injection", "a"])
def test_short_or_unsafe_terms_are_dropped(term):
    session = make_session()
    seed_chunks(session)
    assert keyword_channel(session, "owner/repo", [term]) == []


def test_other_repo_chunks_are_invisible(tmp_path: Path):
    session = make_session()
    seed_chunks(session, repo="other/repo")
    ids = keyword_channel(session, "owner/repo", ["login_user"])
    assert ids == []
