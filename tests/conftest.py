from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  - registers tables
from app.ingest.excel.schema import SheetSpec
from app.models.catalog import Season


@pytest.fixture
def engine(tmp_path: Path):
    """A real file-backed SQLite db per test - foreign keys behave as in production."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def season(session: Session) -> Season:
    from datetime import date

    s = Season(
        code="2025-26",
        name="Süper Lig 2025-26",
        start_date=date(2025, 8, 8),
        end_date=date(2026, 5, 24),
        is_current=True,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


@pytest.fixture
def make_sheet(tmp_path: Path):
    """Write an .xlsx with the given header row and data rows."""

    def _make(
        spec: SheetSpec,
        rows: Sequence[Sequence],
        headers: Sequence[str] | None = None,
        filename: str | None = None,
    ) -> Path:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = spec.key
        worksheet.append(list(headers if headers is not None else spec.headers))
        for row in rows:
            worksheet.append(list(row))
        path = tmp_path / (filename or spec.filename)
        workbook.save(path)
        return path

    return _make
