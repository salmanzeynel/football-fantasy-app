from datetime import date, datetime, timezone

from sqlmodel import Field, SQLModel

from app.models.enums import SourceKind


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProvenanceMixin(SQLModel):
    """Where a row came from.

    Carried by everything we ingest so that when a live API replaces the Excel feed
    in phase 2 we can tell the two apart, and reconcile them where they disagree.
    """

    source: SourceKind = Field(default=SourceKind.EXCEL, index=True)
    source_ref: str | None = Field(default=None, description="Filename or endpoint")
    ingested_at: datetime = Field(default_factory=utcnow)


__all__ = ["ProvenanceMixin", "utcnow", "date"]
