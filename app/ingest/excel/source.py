"""Excel implementation of the DataSource protocol."""

from pathlib import Path

from app.ingest.excel import schema
from app.ingest.excel.reader import read_sheet
from app.ingest.result import ParseResult
from app.ingest.rows import ClubRow, FixtureRow, PlayerRow, StatRow


class ExcelDataSource:
    """Reads the sheets you maintain by hand in data/inbox/.

    Either point it at a directory and rely on the conventional filenames
    (clubs.xlsx, players.xlsx, fixtures.xlsx, stats_gw{n}.xlsx), or pass explicit
    paths per sheet when your files live elsewhere.
    """

    name = "excel"

    def __init__(self, directory: Path, overrides: dict[str, Path] | None = None) -> None:
        self.directory = Path(directory)
        self.overrides = overrides or {}

    def path_for(self, key: str, gameweek: int | None = None) -> Path:
        if key in self.overrides:
            return self.overrides[key]
        if key == "stats":
            if gameweek is None:
                raise ValueError("stats sheets require a gameweek number")
            return self.directory / f"stats_gw{gameweek}.xlsx"
        return self.directory / schema.ALL_SPECS[key].filename

    def fetch_clubs(self) -> ParseResult[ClubRow]:
        return read_sheet(self.path_for("clubs"), schema.CLUBS)

    def fetch_players(self) -> ParseResult[PlayerRow]:
        return read_sheet(self.path_for("players"), schema.PLAYERS)

    def fetch_fixtures(self) -> ParseResult[FixtureRow]:
        return read_sheet(self.path_for("fixtures"), schema.FIXTURES)

    def fetch_gameweek_stats(self, gameweek: int) -> ParseResult[StatRow]:
        return read_sheet(self.path_for("stats", gameweek), schema.STATS)
