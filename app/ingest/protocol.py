"""The seam between "where data comes from" and "what we do with it".

Phase 1: ExcelDataSource reads spreadsheets you maintain by hand.
Phase 2: ApiDataSource calls a live football data provider.

The importer depends on this protocol and on rows.py only, so swapping sources is a
config change plus one new module - no changes to models, services, or the web layer.
"""

from typing import Protocol, runtime_checkable

from app.ingest.result import ParseResult
from app.ingest.rows import ClubRow, FixtureRow, PlayerRow, StatRow


@runtime_checkable
class DataSource(Protocol):
    name: str

    def fetch_clubs(self) -> ParseResult[ClubRow]: ...

    def fetch_players(self) -> ParseResult[PlayerRow]: ...

    def fetch_fixtures(self) -> ParseResult[FixtureRow]: ...

    def fetch_gameweek_stats(self, gameweek: int) -> ParseResult[StatRow]: ...
