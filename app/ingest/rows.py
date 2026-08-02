"""Validated row schemas - the shape every data source must produce.

These are deliberately independent of both the Excel reader and the SQLModel tables.
The Excel source conforms to them today; a live API source will have to conform to
them in phase 2. That is what keeps the swap cheap.
"""

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import FixtureStatus, PlayerStatus, Position


def _blank_to_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v


class RowBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


class CodeMixin(RowBase):
    """Business keys are upper-cased on the way in.

    Codes are how every import matches an existing record. Normalising case here means
    'gs' and 'GS' in your spreadsheet can never silently become two different clubs.
    """

    @staticmethod
    def _norm_code(v: str) -> str:
        v = str(v).strip().upper()
        if not v:
            raise ValueError("code must not be empty")
        return v


class ClubRow(CodeMixin):
    club_code: str
    name: str
    short_name: str
    city: str | None = None
    primary_color: str | None = None

    _n = field_validator("club_code", mode="before")(lambda v: CodeMixin._norm_code(v))
    _b = field_validator("city", "primary_color", mode="before")(_blank_to_none)


class PlayerRow(CodeMixin):
    player_code: str
    full_name: str
    display_name: str
    club_code: str
    position: Position
    price: float = Field(default=0.0, ge=0)
    birth_date: date | None = None
    nationality: str | None = None
    shirt_number: int | None = None
    status: PlayerStatus = PlayerStatus.ACTIVE

    _n = field_validator("player_code", "club_code", mode="before")(
        lambda v: CodeMixin._norm_code(v)
    )
    _b = field_validator(
        "birth_date", "nationality", "shirt_number", "price", "status", mode="before"
    )(_blank_to_none)

    @field_validator("position", mode="before")
    @classmethod
    def _position(cls, v):
        if v is None:
            raise ValueError("position is required (one of GK, DEF, MID, FWD)")
        return str(v).strip().upper()

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v):
        if v is None:
            return PlayerStatus.ACTIVE
        return str(v).strip().lower()

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, v):
        return 0.0 if v is None else v

    @field_validator("birth_date", mode="before")
    @classmethod
    def _birth_date(cls, v):
        if isinstance(v, datetime):
            return v.date()
        return v


class FixtureRow(CodeMixin):
    fixture_code: str
    gameweek: int = Field(ge=1, le=60)
    kickoff_utc: datetime
    home_club_code: str
    away_club_code: str
    status: FixtureStatus = FixtureStatus.SCHEDULED
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)

    _n = field_validator("fixture_code", "home_club_code", "away_club_code", mode="before")(
        lambda v: CodeMixin._norm_code(v)
    )
    _b = field_validator("home_score", "away_score", "status", mode="before")(_blank_to_none)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v):
        if v is None:
            return FixtureStatus.SCHEDULED
        return str(v).strip().lower()

    @field_validator("kickoff_utc", mode="before")
    @classmethod
    def _kickoff(cls, v):
        if v is None:
            raise ValueError("kickoff_utc is required")
        return v

    @field_validator("kickoff_utc", mode="after")
    @classmethod
    def _as_utc(cls, v: datetime) -> datetime:
        # Excel hands back naive datetimes. The column is documented as UTC, so
        # attach UTC rather than guessing the author's local zone.
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _sane(self):
        if self.home_club_code == self.away_club_code:
            raise ValueError("home_club_code and away_club_code must differ")
        if self.status is FixtureStatus.FINAL and (
            self.home_score is None or self.away_score is None
        ):
            raise ValueError("a final fixture needs both home_score and away_score")
        return self


class StatRow(CodeMixin):
    """Per-player, per-fixture raw stats.

    Parsed and validated in phase 1 so the templates and reader are ready, but not yet
    written to the database - that lands with the scoring engine in M7.
    """

    fixture_code: str
    player_code: str
    minutes: int = Field(default=0, ge=0, le=120)
    goals: int = Field(default=0, ge=0)
    assists: int = Field(default=0, ge=0)
    shots: int = Field(default=0, ge=0)
    key_passes: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    pens_saved: int = Field(default=0, ge=0)
    pens_missed: int = Field(default=0, ge=0)
    goals_conceded: int = Field(default=0, ge=0)
    own_goals: int = Field(default=0, ge=0)
    yellow_cards: int = Field(default=0, ge=0, le=2)
    red_cards: int = Field(default=0, ge=0, le=1)
    motm: bool = False

    _n = field_validator("fixture_code", "player_code", mode="before")(
        lambda v: CodeMixin._norm_code(v)
    )

    @field_validator(
        "minutes",
        "goals",
        "assists",
        "shots",
        "key_passes",
        "saves",
        "pens_saved",
        "pens_missed",
        "goals_conceded",
        "own_goals",
        "yellow_cards",
        "red_cards",
        mode="before",
    )
    @classmethod
    def _blank_zero(cls, v):
        return 0 if _blank_to_none(v) is None else v

    @field_validator("motm", mode="before")
    @classmethod
    def _motm(cls, v):
        if _blank_to_none(v) is None:
            return False
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "y", "evet"}
        return bool(v)
