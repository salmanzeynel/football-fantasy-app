"""Turn validated rows into database records.

Four rules, all of them load-bearing (docs/PLAN.md section 5):

1. Idempotent - upsert keyed on the business code, so re-running an import is a no-op.
2. Dry-run - do the whole thing, report it, roll it back.
3. Loud on bad references - a player pointing at an unknown club is an error, not a null.
4. Whole-file transaction - if any row is bad, nothing is written.

This module knows nothing about Excel. It takes ParseResults, so a live API source in
phase 2 feeds the exact same code path.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlmodel import Session, select

from app.ingest.result import ImportReport, ParseResult, RowError
from app.ingest.rows import ClubRow, FixtureRow, PlayerRow
from app.models.catalog import Club, Fixture, Gameweek, Player, Season
from app.models.enums import SourceKind

T = TypeVar("T")


def _as_naive_utc(value: datetime) -> datetime:
    """SQLite columns are timezone-naive, so store a consistent UTC wall-clock.

    Without this, an aware value from the sheet never compares equal to the naive value
    read back from the database, and every re-import would look like a change.
    """
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _duplicate_errors(
    parse: ParseResult[T], key: Callable[[T], str], label: str
) -> list[RowError]:
    counts = Counter(key(row) for _, row in parse.rows)
    dupes = {code for code, n in counts.items() if n > 1}
    return [
        RowError(parse.sheet, number, label, f"duplicate {label} '{key(row)}' in this file")
        for number, row in parse.rows
        if key(row) in dupes
    ]


def _apply(obj: Any, values: dict[str, Any]) -> bool:
    """Set only the fields that actually differ. Returns True if anything changed."""
    changed = False
    for name, value in values.items():
        if getattr(obj, name) != value:
            setattr(obj, name, value)
            changed = True
    return changed


def _stamp(obj: Any, source_ref: str | None, source: SourceKind) -> None:
    obj.source = source
    obj.source_ref = source_ref
    obj.ingested_at = datetime.now(timezone.utc)


def _finish(session: Session, report: ImportReport, dry_run: bool) -> ImportReport:
    if not report.ok:
        session.rollback()
        return report
    session.flush()
    if dry_run:
        session.rollback()
        report.notes.append("dry run - all changes rolled back, nothing was written")
    else:
        session.commit()
    return report


# --------------------------------------------------------------------------- clubs


def import_clubs(
    session: Session,
    parse: ParseResult[ClubRow],
    *,
    source_ref: str | None = None,
    source: SourceKind = SourceKind.EXCEL,
    dry_run: bool = False,
) -> ImportReport:
    report = ImportReport(sheet=parse.sheet, dry_run=dry_run)
    report.errors.extend(parse.errors)
    report.errors.extend(_duplicate_errors(parse, lambda r: r.club_code, "club_code"))
    if report.errors:
        return _finish(session, report, dry_run)

    existing = {c.club_code: c for c in session.exec(select(Club)).all()}

    for _number, row in parse.rows:
        values = {
            "name": row.name,
            "short_name": row.short_name,
            "city": row.city,
            "primary_color": row.primary_color,
        }
        club = existing.get(row.club_code)
        if club is None:
            club = Club(club_code=row.club_code, **values)
            _stamp(club, source_ref, source)
            session.add(club)
            report.created += 1
        elif _apply(club, values):
            _stamp(club, source_ref, source)
            report.updated += 1
        else:
            report.unchanged += 1

    return _finish(session, report, dry_run)


# -------------------------------------------------------------------------- players


def import_players(
    session: Session,
    parse: ParseResult[PlayerRow],
    *,
    source_ref: str | None = None,
    source: SourceKind = SourceKind.EXCEL,
    dry_run: bool = False,
) -> ImportReport:
    report = ImportReport(sheet=parse.sheet, dry_run=dry_run)
    report.errors.extend(parse.errors)
    report.errors.extend(_duplicate_errors(parse, lambda r: r.player_code, "player_code"))

    clubs = {c.club_code: c for c in session.exec(select(Club)).all()}
    for number, row in parse.rows:
        if row.club_code not in clubs:
            report.errors.append(
                RowError(
                    parse.sheet,
                    number,
                    "club_code",
                    f"unknown club '{row.club_code}' - import clubs.xlsx first",
                )
            )
    if report.errors:
        return _finish(session, report, dry_run)

    existing = {p.player_code: p for p in session.exec(select(Player)).all()}

    for _number, row in parse.rows:
        values = {
            "full_name": row.full_name,
            "display_name": row.display_name,
            "club_id": clubs[row.club_code].id,
            "position": row.position,
            "price": float(row.price),
            "birth_date": row.birth_date,
            "nationality": row.nationality,
            "shirt_number": row.shirt_number,
            "status": row.status,
        }
        player = existing.get(row.player_code)
        if player is None:
            player = Player(player_code=row.player_code, **values)
            _stamp(player, source_ref, source)
            session.add(player)
            report.created += 1
        elif _apply(player, values):
            _stamp(player, source_ref, source)
            report.updated += 1
        else:
            report.unchanged += 1

    return _finish(session, report, dry_run)


# ------------------------------------------------------------------------- fixtures


def import_fixtures(
    session: Session,
    parse: ParseResult[FixtureRow],
    *,
    season: Season,
    source_ref: str | None = None,
    source: SourceKind = SourceKind.EXCEL,
    dry_run: bool = False,
) -> ImportReport:
    report = ImportReport(sheet=parse.sheet, dry_run=dry_run)
    report.errors.extend(parse.errors)
    report.errors.extend(_duplicate_errors(parse, lambda r: r.fixture_code, "fixture_code"))

    clubs = {c.club_code: c for c in session.exec(select(Club)).all()}
    for number, row in parse.rows:
        for field in ("home_club_code", "away_club_code"):
            code = getattr(row, field)
            if code not in clubs:
                report.errors.append(
                    RowError(
                        parse.sheet,
                        number,
                        field,
                        f"unknown club '{code}' - import clubs.xlsx first",
                    )
                )
    if report.errors:
        return _finish(session, report, dry_run)

    gameweeks = _ensure_gameweeks(
        session, season, sorted({row.gameweek for _, row in parse.rows}), report
    )
    existing = {
        f.fixture_code: f
        for f in session.exec(select(Fixture).where(Fixture.season_id == season.id)).all()
    }

    for _number, row in parse.rows:
        values = {
            "season_id": season.id,
            "gameweek_id": gameweeks[row.gameweek].id,
            "kickoff_utc": _as_naive_utc(row.kickoff_utc),
            "home_club_id": clubs[row.home_club_code].id,
            "away_club_id": clubs[row.away_club_code].id,
            "status": row.status,
            "home_score": row.home_score,
            "away_score": row.away_score,
        }
        fixture = existing.get(row.fixture_code)
        if fixture is None:
            fixture = Fixture(fixture_code=row.fixture_code, **values)
            _stamp(fixture, source_ref, source)
            session.add(fixture)
            report.created += 1
        elif _apply(fixture, values):
            _stamp(fixture, source_ref, source)
            report.updated += 1
        else:
            report.unchanged += 1

    session.flush()
    _refresh_deadlines(session, gameweeks.values(), report)

    return _finish(session, report, dry_run)


def _ensure_gameweeks(
    session: Session, season: Season, numbers: Sequence[int], report: ImportReport
) -> dict[int, Gameweek]:
    found = {
        gw.number: gw
        for gw in session.exec(select(Gameweek).where(Gameweek.season_id == season.id)).all()
    }
    created = 0
    for number in numbers:
        if number not in found:
            gameweek = Gameweek(season_id=season.id, number=number)
            session.add(gameweek)
            found[number] = gameweek
            created += 1
    if created:
        session.flush()
        report.notes.append(f"created {created} gameweek(s)")
    return found


def _refresh_deadlines(
    session: Session, gameweeks: "Sequence[Gameweek]", report: ImportReport
) -> None:
    """The deadline is the first kickoff of the gameweek - that is when lineups lock."""
    moved = 0
    for gameweek in gameweeks:
        kickoffs = session.exec(
            select(Fixture.kickoff_utc).where(Fixture.gameweek_id == gameweek.id)
        ).all()
        if not kickoffs:
            continue
        earliest = min(kickoffs)
        if gameweek.deadline_utc != earliest:
            gameweek.deadline_utc = earliest
            moved += 1
    if moved:
        report.notes.append(f"recalculated deadline for {moved} gameweek(s)")
