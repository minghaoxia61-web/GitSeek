from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from packages.domain.models import Base
from packages.domain.settings import get_settings


def create_db_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    url = database_url or get_settings().database_url
    connect_args = {"connect_timeout": 3} if url.startswith("postgresql") else {}
    return create_engine(url, echo=echo, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@lru_cache
def ensure_database_schema(engine: Engine) -> bool:
    """Create missing tables for zero-touch deployments without altering existing data."""
    try:
        Base.metadata.create_all(engine)
        return True
    except SQLAlchemyError:
        return False


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    engine = create_db_engine()
    ensure_database_schema(engine)
    return create_session_factory(engine)
