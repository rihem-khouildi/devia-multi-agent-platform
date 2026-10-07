from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from api.db_models import Base
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None
_database_ready = False
_initialized_url: Optional[str] = None

# SQLite fallback path — used when DATABASE_URL is not configured
_SQLITE_FALLBACK_URL = "sqlite:///./devia_local.db"


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    # sqlite:// and other drivers pass through unchanged
    return url


def _engine_kwargs(url: str) -> dict:
    """SQLite requires connect_args for thread safety; other drivers don't."""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def initialize_database(settings: Settings) -> bool:
    global _engine, _SessionLocal, _database_ready, _initialized_url

    raw_url = settings.database.url
    if not raw_url:
        # No PostgreSQL configured — fall back to local SQLite so that user
        # accounts and other DB-backed data survive between requests/restarts.
        raw_url = _SQLITE_FALLBACK_URL
        logger.info("DATABASE_URL not configured; using SQLite fallback at devia_local.db")

    normalized_url = _normalize_database_url(raw_url)
    if _engine is not None and _initialized_url == normalized_url and _database_ready:
        return True

    try:
        engine = create_engine(normalized_url, future=True, **_engine_kwargs(normalized_url))
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        Base.metadata.create_all(engine)

        _engine = engine
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
        _database_ready = True
        _initialized_url = normalized_url
        logger.info("Database initialized: %s", normalized_url.split("@")[-1] if "@" in normalized_url else normalized_url)
        return True
    except SQLAlchemyError as exc:
        _engine = None
        _SessionLocal = None
        _database_ready = False
        _initialized_url = normalized_url
        logger.warning("Database unavailable; falling back to in-memory stores: %s", exc)
        return False


def is_database_ready() -> bool:
    return _database_ready and _SessionLocal is not None


def get_backend_name() -> str:
    """Human-readable name of the active DB backend."""
    if not _initialized_url:
        return "in-memory"
    if "postgresql" in _initialized_url:
        return "postgresql"
    if "sqlite" in _initialized_url:
        return "sqlite (local fallback)"
    return _initialized_url.split(":")[0]


@contextmanager
def session_scope() -> Iterator[Optional[Session]]:
    if not is_database_ready():
        yield None
        return

    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("Database operation failed; caller should fall back if possible: %s", exc)
        raise
    finally:
        session.close()
