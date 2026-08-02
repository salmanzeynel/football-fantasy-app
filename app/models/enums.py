from enum import Enum


class Position(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


class PlayerStatus(str, Enum):
    ACTIVE = "active"
    INJURED = "injured"
    SUSPENDED = "suspended"
    UNAVAILABLE = "unavailable"


class FixtureStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINAL = "final"
    POSTPONED = "postponed"


class SourceKind(str, Enum):
    EXCEL = "excel"
    API = "api"
    SEED = "seed"
