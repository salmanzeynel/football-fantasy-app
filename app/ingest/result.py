"""Error and result types shared by every stage of ingest."""

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RowError:
    """A problem with one row, addressed the way the user sees it: sheet + row number."""

    sheet: str
    row: int | None
    field: str | None
    message: str

    def __str__(self) -> str:
        where = f"{self.sheet}"
        if self.row is not None:
            where += f" row {self.row}"
        if self.field:
            where += f" [{self.field}]"
        return f"{where}: {self.message}"


@dataclass
class ParseResult(Generic[T]):
    """Rows that validated, plus every row that did not."""

    sheet: str
    rows: list[tuple[int, T]] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ImportReport:
    sheet: str
    dry_run: bool = False
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: list[RowError] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged
