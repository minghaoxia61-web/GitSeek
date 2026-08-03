from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from packages.domain.settings import get_settings


def create_db_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)

