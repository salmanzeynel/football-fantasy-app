"""Importing this package registers every table on SQLModel.metadata.

Alembic autogenerate and db.create_all() both depend on that, so any new model
module must be imported here.
"""

from app.models.catalog import Club, Fixture, Gameweek, Player, Season
from app.models.enums import FixtureStatus, PlayerStatus, Position, SourceKind
from app.models.identity import User

__all__ = [
    "Club",
    "Fixture",
    "FixtureStatus",
    "Gameweek",
    "Player",
    "PlayerStatus",
    "Position",
    "Season",
    "SourceKind",
    "User",
]
