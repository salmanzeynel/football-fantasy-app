"""The header contract for each sheet type.

The header row *is* the interface. The reader validates it exactly and refuses to
guess at near-misses - a silently mis-mapped column is far more expensive than a
loud failure.
"""

from dataclasses import dataclass

from app.ingest.rows import ClubRow, FixtureRow, PlayerRow, StatRow


@dataclass(frozen=True)
class Column:
    name: str
    required: bool
    help: str
    example: str = ""


@dataclass(frozen=True)
class SheetSpec:
    key: str
    filename: str
    row_model: type
    columns: tuple[Column, ...]

    @property
    def headers(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    @property
    def required_headers(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns if c.required)


CLUBS = SheetSpec(
    key="clubs",
    filename="clubs.xlsx",
    row_model=ClubRow,
    columns=(
        Column("club_code", True, "Stable unique id you invent. Never reuse or change.", "GS"),
        Column("name", True, "Full club name", "Galatasaray SK"),
        Column("short_name", True, "3-6 chars, used in tables", "GAL"),
        Column("city", False, "Home city", "Istanbul"),
        Column("primary_color", False, "Hex colour for the UI", "#A90432"),
    ),
)

PLAYERS = SheetSpec(
    key="players",
    filename="players.xlsx",
    row_model=PlayerRow,
    columns=(
        Column("player_code", True, "Stable unique id you invent. Never reuse or change.", "GS-MUSLERA-1"),
        Column("full_name", True, "Full legal name", "Fernando Muslera"),
        Column("display_name", True, "Short name shown in the UI", "Muslera"),
        Column("club_code", True, "Must exist in clubs.xlsx", "GS"),
        Column("position", True, "One of: GK, DEF, MID, FWD", "GK"),
        Column("price", False, "Market value. Display/ranking only in a snake draft.", "8.5"),
        Column("birth_date", False, "YYYY-MM-DD", "1986-06-16"),
        Column("nationality", False, "Country", "Uruguay"),
        Column("shirt_number", False, "Squad number", "1"),
        Column("status", False, "active | injured | suspended | unavailable", "active"),
    ),
)

FIXTURES = SheetSpec(
    key="fixtures",
    filename="fixtures.xlsx",
    row_model=FixtureRow,
    columns=(
        Column("fixture_code", True, "Stable unique id you invent.", "GW1-GS-FB"),
        Column("gameweek", True, "Gameweek number, 1-34", "1"),
        Column("kickoff_utc", True, "Kickoff in UTC, not Istanbul time", "2025-08-08 18:00"),
        Column("home_club_code", True, "Must exist in clubs.xlsx", "GS"),
        Column("away_club_code", True, "Must exist in clubs.xlsx", "FB"),
        Column("status", False, "scheduled | live | final | postponed", "scheduled"),
        Column("home_score", False, "Fill after the match", ""),
        Column("away_score", False, "Fill after the match", ""),
    ),
)

STATS = SheetSpec(
    key="stats",
    filename="stats_gw1.xlsx",
    row_model=StatRow,
    columns=(
        Column("fixture_code", True, "Must exist in fixtures.xlsx", "GW1-GS-FB"),
        Column("player_code", True, "Must exist in players.xlsx", "GS-MUSLERA-1"),
        Column("minutes", False, "Minutes played, 0-120", "90"),
        Column("goals", False, "Goals scored", "0"),
        Column("assists", False, "Assists", "0"),
        Column("shots", False, "Shots", "0"),
        Column("key_passes", False, "Key passes", "0"),
        Column("saves", False, "Saves (goalkeepers)", "4"),
        Column("pens_saved", False, "Penalties saved", "0"),
        Column("pens_missed", False, "Penalties missed", "0"),
        Column("goals_conceded", False, "Goals conceded while on pitch", "1"),
        Column("own_goals", False, "Own goals", "0"),
        Column("yellow_cards", False, "0-2", "0"),
        Column("red_cards", False, "0-1", "0"),
        Column("motm", False, "Man of the match: yes/no", "no"),
    ),
)

ALL_SPECS: dict[str, SheetSpec] = {s.key: s for s in (CLUBS, PLAYERS, FIXTURES, STATS)}
