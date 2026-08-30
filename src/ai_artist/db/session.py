"""Database session management."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Global session factory (initialized on first use)
_session_factory: sessionmaker | None = None


def get_session_factory() -> sessionmaker:
    """Get or create the global session factory."""
    global _session_factory
    if _session_factory is None:
        # Default to a database in the current directory
        db_path = Path.cwd() / "data" / "ai_artist.db"
        _session_factory = create_session_factory(db_path)
    return _session_factory


def set_session_factory(session_factory: sessionmaker) -> None:
    """Set the global session factory."""
    global _session_factory
    _session_factory = session_factory


def create_db_engine(db_path: Path) -> Engine:
    """Create SQLite engine with optimal settings."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    # Enable WAL mode for better concurrency
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
        conn.commit()

    return engine


def create_session_factory(db_path: Path) -> sessionmaker:
    """Create session factory."""
    engine = create_db_engine(db_path)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_db_session(session_factory: sessionmaker) -> Iterator[Session]:
    """Context manager for database sessions."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions.

    Yields:
        Database session
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
