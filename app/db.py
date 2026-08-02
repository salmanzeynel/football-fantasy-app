from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _record):
    """SQLite ignores foreign keys unless asked. We rely on them for referential integrity."""
    if _settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_all() -> None:
    """Create tables directly. Alembic is the real path; this is for tests and quick bootstraps."""
    import app.models  # noqa: F401  - registers tables on SQLModel.metadata

    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(engine) as session:
        yield session
