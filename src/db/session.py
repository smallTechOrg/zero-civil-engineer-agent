from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite does not create parent directories — do it before connecting."""
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.endswith(":memory:"):
        Path(url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from config.settings import get_settings
        url = get_settings().database_url
        _ensure_sqlite_dir(url)
        _engine = create_engine(url, echo=False)
    return _engine


def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    with _get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def create_db_session() -> Generator[Session, None, None]:
    """Standalone — for graph nodes, CLI, scripts."""
    with _get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def init_db() -> None:
    from db.models import Base
    Base.metadata.create_all(bind=_get_engine())
