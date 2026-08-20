"""SQLAlchemy engine/session — optional until DATABASE_URL is set."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import database_url, is_production

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def reset_engine() -> None:
    """Test helper — drop cached engine after DATABASE_URL changes."""
    global _engine, _SessionLocal
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _SessionLocal = None


def get_engine() -> Optional[Engine]:
    global _engine, _SessionLocal
    url = database_url()
    if not url:
        return None
    if _engine is None:
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("postgresql"):
            kwargs["connect_args"] = {"connect_timeout": 5}
        elif url.startswith("sqlite"):
            # Heartbeat/worker threads share the engine in tests.
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def database_reachable() -> bool:
    engine = get_engine()
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False


def require_database() -> Engine:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return engine


@contextmanager
def session_scope() -> Iterator[Session]:
    engine = require_database()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def db_required_at_startup() -> bool:
    """Production with DATABASE_URL must be reachable; missing URL in prod is a startup fail."""
    if not is_production():
        return False
    return True
