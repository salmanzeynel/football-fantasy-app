"""The four importer rules from docs/PLAN.md section 5, one test group each."""

from sqlmodel import select

from app.ingest.excel import schema
from app.ingest.excel.reader import read_sheet
from app.ingest.importer import import_clubs, import_fixtures, import_players
from app.models.catalog import Club, Fixture, Gameweek, Player

CLUBS = [
    ["GS", "Galatasaray SK", "GAL", "Istanbul", "#A90432"],
    ["FB", "Fenerbahçe SK", "FEN", "Istanbul", "#0A1F5C"],
    ["BJK", "Beşiktaş JK", "BJK", "Istanbul", "#000000"],
]

PLAYERS = [
    ["GS-MUSLERA", "Fernando Muslera", "Muslera", "GS", "GK", 8.5, "1986-06-16", "Uruguay", 1, "active"],
    ["GS-ICARDI", "Mauro Icardi", "Icardi", "GS", "FWD", 11.0, "1993-02-19", "Argentina", 9, "active"],
    ["FB-DZEKO", "Edin Džeko", "Džeko", "FB", "FWD", 9.5, "1986-03-17", "Bosnia", 11, "active"],
]

FIXTURES = [
    ["GW1-GS-FB", 1, "2025-08-10 18:00", "GS", "FB", "scheduled", None, None],
    ["GW1-BJK-GS", 1, "2025-08-09 15:00", "BJK", "GS", "scheduled", None, None],
    ["GW2-FB-BJK", 2, "2025-08-17 18:00", "FB", "BJK", "scheduled", None, None],
]


def _load(make_sheet, spec, rows):
    return read_sheet(make_sheet(spec, rows), spec)


def _seed_clubs(session, make_sheet):
    return import_clubs(session, _load(make_sheet, schema.CLUBS, CLUBS))


# ------------------------------------------------------------------ rule 1: idempotent


def test_import_creates_records(session, make_sheet):
    report = _seed_clubs(session, make_sheet)
    assert report.ok
    assert (report.created, report.updated, report.unchanged) == (3, 0, 0)
    assert len(session.exec(select(Club)).all()) == 3


def test_reimporting_identical_file_changes_nothing(session, make_sheet):
    _seed_clubs(session, make_sheet)
    report = _seed_clubs(session, make_sheet)
    assert (report.created, report.updated, report.unchanged) == (0, 0, 3)
    assert len(session.exec(select(Club)).all()) == 3


def test_changed_field_is_detected_as_update(session, make_sheet):
    _seed_clubs(session, make_sheet)
    edited = [["GS", "Galatasaray Spor Kulübü", "GAL", "Istanbul", "#A90432"], *CLUBS[1:]]
    report = import_clubs(session, _load(make_sheet, schema.CLUBS, edited))
    assert (report.created, report.updated, report.unchanged) == (0, 1, 2)
    club = session.exec(select(Club).where(Club.club_code == "GS")).one()
    assert club.name == "Galatasaray Spor Kulübü"


def test_reimporting_players_is_idempotent(session, make_sheet):
    _seed_clubs(session, make_sheet)
    import_players(session, _load(make_sheet, schema.PLAYERS, PLAYERS))
    report = import_players(session, _load(make_sheet, schema.PLAYERS, PLAYERS))
    assert (report.created, report.updated, report.unchanged) == (0, 0, 3)


def test_reimporting_fixtures_is_idempotent(session, make_sheet, season):
    _seed_clubs(session, make_sheet)
    parse = _load(make_sheet, schema.FIXTURES, FIXTURES)
    import_fixtures(session, parse, season=season)
    report = import_fixtures(session, _load(make_sheet, schema.FIXTURES, FIXTURES), season=season)
    assert (report.created, report.updated, report.unchanged) == (0, 0, 3)


# --------------------------------------------------------------------- rule 2: dry run


def test_dry_run_writes_nothing(session, make_sheet):
    report = import_clubs(session, _load(make_sheet, schema.CLUBS, CLUBS), dry_run=True)
    assert report.ok
    assert report.created == 3
    assert session.exec(select(Club)).all() == []


def test_dry_run_still_reports_errors(session, make_sheet):
    bad = [*CLUBS, ["GS", "Duplicate", "DUP", None, None]]
    report = import_clubs(session, _load(make_sheet, schema.CLUBS, bad), dry_run=True)
    assert not report.ok


# ------------------------------------------------------------ rule 3: loud on bad refs


def test_unknown_club_reference_is_an_error(session, make_sheet):
    _seed_clubs(session, make_sheet)
    rows = [["TS-X", "Someone", "Someone", "TS", "MID", 5.0, None, None, None, None]]
    report = import_players(session, _load(make_sheet, schema.PLAYERS, rows))
    assert not report.ok
    assert "unknown club 'TS'" in report.errors[0].message
    assert report.errors[0].row == 2


def test_duplicate_code_within_a_file_is_an_error(session, make_sheet):
    rows = [*CLUBS, ["FB", "Fenerbahce again", "FEN", None, None]]
    report = import_clubs(session, _load(make_sheet, schema.CLUBS, rows))
    assert not report.ok
    assert all("duplicate" in e.message for e in report.errors)


def test_fixture_with_unknown_club_is_an_error(session, make_sheet, season):
    _seed_clubs(session, make_sheet)
    rows = [["GW1-X-Y", 1, "2025-08-10 18:00", "GS", "TS", None, None, None]]
    report = import_fixtures(session, _load(make_sheet, schema.FIXTURES, rows), season=season)
    assert not report.ok
    assert "unknown club 'TS'" in report.errors[0].message


# ------------------------------------------------- rule 4: whole-file transaction


def test_one_bad_row_prevents_the_whole_file(session, make_sheet):
    _seed_clubs(session, make_sheet)
    rows = [
        ["GS-NEW", "Valid Player", "Valid", "GS", "MID", 6.0, None, None, None, None],
        ["FB-BAD", "Bad Ref", "Bad", "NOPE", "MID", 6.0, None, None, None, None],
    ]
    report = import_players(session, _load(make_sheet, schema.PLAYERS, rows))
    assert not report.ok
    assert session.exec(select(Player)).all() == [], "valid rows must not sneak through"


def test_failed_import_leaves_earlier_data_intact(session, make_sheet):
    _seed_clubs(session, make_sheet)
    import_players(session, _load(make_sheet, schema.PLAYERS, PLAYERS))
    bad = [["X", "Bad", "Bad", "NOPE", "MID", 1.0, None, None, None, None]]
    import_players(session, _load(make_sheet, schema.PLAYERS, bad))
    assert len(session.exec(select(Player)).all()) == 3


# ------------------------------------------------------ fixtures: gameweeks + deadlines


def test_gameweeks_are_created_from_fixtures(session, make_sheet, season):
    _seed_clubs(session, make_sheet)
    report = import_fixtures(session, _load(make_sheet, schema.FIXTURES, FIXTURES), season=season)
    assert report.ok
    numbers = sorted(gw.number for gw in session.exec(select(Gameweek)).all())
    assert numbers == [1, 2]


def test_deadline_is_the_first_kickoff_of_the_gameweek(session, make_sheet, season):
    _seed_clubs(session, make_sheet)
    import_fixtures(session, _load(make_sheet, schema.FIXTURES, FIXTURES), season=season)
    gw1 = session.exec(select(Gameweek).where(Gameweek.number == 1)).one()
    # GW1 has an 09 Aug and a 10 Aug kickoff; the earlier one is the lock time.
    assert gw1.deadline_utc.isoformat() == "2025-08-09T15:00:00"


def test_scores_can_be_filled_in_later(session, make_sheet, season):
    _seed_clubs(session, make_sheet)
    import_fixtures(session, _load(make_sheet, schema.FIXTURES, FIXTURES), season=season)
    played = [["GW1-GS-FB", 1, "2025-08-10 18:00", "GS", "FB", "final", 2, 1], *FIXTURES[1:]]
    report = import_fixtures(session, _load(make_sheet, schema.FIXTURES, played), season=season)
    assert (report.created, report.updated, report.unchanged) == (0, 1, 2)
    fixture = session.exec(select(Fixture).where(Fixture.fixture_code == "GW1-GS-FB")).one()
    assert (fixture.home_score, fixture.away_score) == (2, 1)


def test_player_club_transfer_is_applied(session, make_sheet):
    _seed_clubs(session, make_sheet)
    import_players(session, _load(make_sheet, schema.PLAYERS, PLAYERS))
    transferred = [
        ["GS-ICARDI", "Mauro Icardi", "Icardi", "FB", "FWD", 11.0, "1993-02-19", "Argentina", 9, "active"],
    ]
    report = import_players(session, _load(make_sheet, schema.PLAYERS, transferred))
    assert report.updated == 1
    player = session.exec(select(Player).where(Player.player_code == "GS-ICARDI")).one()
    club = session.get(Club, player.club_id)
    assert club.club_code == "FB"
