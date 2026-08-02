"""The real-world football catalog: seasons, clubs, players, gameweeks, fixtures.

Everything here is ingested from an external source (Excel in phase 1, an API later).
Nothing in here is fantasy-specific - no users, teams, or scores.

Business keys are the `*_code` columns, not the integer primary keys. Imports upsert
on those codes, so they must be stable forever. See docs/PLAN.md section 10.
"""

from datetime import date, datetime

from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from app.models.base import ProvenanceMixin
from app.models.enums import FixtureStatus, PlayerStatus, Position


class Season(SQLModel, table=True):
    __tablename__ = "season"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True, description="e.g. 2025-26")
    name: str
    start_date: date
    end_date: date
    is_current: bool = Field(default=False)

    gameweeks: list["Gameweek"] = Relationship(back_populates="season")
    fixtures: list["Fixture"] = Relationship(back_populates="season")


class Club(ProvenanceMixin, table=True):
    __tablename__ = "club"

    id: int | None = Field(default=None, primary_key=True)
    club_code: str = Field(index=True, unique=True)
    name: str
    short_name: str
    city: str | None = None
    primary_color: str | None = None

    players: list["Player"] = Relationship(back_populates="club")


class Player(ProvenanceMixin, table=True):
    __tablename__ = "player"

    id: int | None = Field(default=None, primary_key=True)
    player_code: str = Field(index=True, unique=True)
    full_name: str
    display_name: str
    club_id: int = Field(foreign_key="club.id", index=True)
    position: Position = Field(index=True)
    price: float = Field(
        default=0.0,
        description=(
            "Market value in league units. Phase 1 uses a snake draft, so price is "
            "display/ranking metadata only - it does not gate acquisition. It becomes "
            "load-bearing if auction drafts are enabled later."
        ),
    )
    birth_date: date | None = None
    nationality: str | None = None
    shirt_number: int | None = None
    status: PlayerStatus = Field(default=PlayerStatus.ACTIVE, index=True)

    club: Club | None = Relationship(back_populates="players")


class Gameweek(SQLModel, table=True):
    __tablename__ = "gameweek"
    __table_args__ = (UniqueConstraint("season_id", "number", name="uq_gameweek_season_number"),)

    id: int | None = Field(default=None, primary_key=True)
    season_id: int = Field(foreign_key="season.id", index=True)
    number: int = Field(index=True)
    deadline_utc: datetime | None = Field(
        default=None,
        description="First kickoff of the gameweek. Lineups lock here. Derived on fixture import.",
    )
    is_complete: bool = Field(default=False)

    season: Season | None = Relationship(back_populates="gameweeks")
    fixtures: list["Fixture"] = Relationship(back_populates="gameweek")


class Fixture(ProvenanceMixin, table=True):
    __tablename__ = "fixture"

    id: int | None = Field(default=None, primary_key=True)
    fixture_code: str = Field(index=True, unique=True)
    season_id: int = Field(foreign_key="season.id", index=True)
    gameweek_id: int = Field(foreign_key="gameweek.id", index=True)
    kickoff_utc: datetime
    home_club_id: int = Field(foreign_key="club.id", index=True)
    away_club_id: int = Field(foreign_key="club.id", index=True)
    status: FixtureStatus = Field(default=FixtureStatus.SCHEDULED, index=True)
    home_score: int | None = None
    away_score: int | None = None

    season: Season | None = Relationship(back_populates="fixtures")
    gameweek: Gameweek | None = Relationship(back_populates="fixtures")
