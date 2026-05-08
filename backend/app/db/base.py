"""SQLAlchemy sync engine + session factory + declarative Base.

Sync chosen because the stream loop runs in worker threads — easier to
write to the DB directly from those threads than to bridge them into an
async event loop.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Common declarative base for all ORM entities."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            echo=settings.DB_ECHO,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False, future=True
        )
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a Session."""
    factory = get_session_factory()
    with factory() as session:
        yield session


def session_scope() -> Session:
    """Open a session for thread-local synchronous use (stream loop)."""
    return get_session_factory()()


def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _session_factory = None
