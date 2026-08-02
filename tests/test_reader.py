"""The header row is the contract, and errors must point at a spreadsheet row."""

from app.ingest.excel import schema
from app.ingest.excel.reader import read_sheet
from app.models.enums import PlayerStatus, Position

CLUB_ROWS = [
    ["GS", "Galatasaray SK", "GAL", "Istanbul", "#A90432"],
    ["FB", "Fenerbahçe SK", "FEN", "Istanbul", "#0A1F5C"],
]


def test_reads_valid_rows(make_sheet):
    result = read_sheet(make_sheet(schema.CLUBS, CLUB_ROWS), schema.CLUBS)
    assert result.ok
    assert [row.club_code for _, row in result.rows] == ["GS", "FB"]


def test_codes_are_upper_cased(make_sheet):
    result = read_sheet(
        make_sheet(schema.CLUBS, [["  gs  ", "Galatasaray SK", "GAL", None, None]]), schema.CLUBS
    )
    assert result.ok
    assert result.rows[0][1].club_code == "GS"


def test_missing_required_column_is_rejected(make_sheet):
    headers = [h for h in schema.CLUBS.headers if h != "short_name"]
    result = read_sheet(
        make_sheet(schema.CLUBS, [["GS", "Galatasaray SK", "Istanbul", "#A90432"]], headers=headers),
        schema.CLUBS,
    )
    assert not result.ok
    assert "short_name" in result.errors[0].message


def test_unknown_column_is_rejected_rather_than_guessed(make_sheet):
    headers = [*schema.CLUBS.headers, "stadium"]
    result = read_sheet(
        make_sheet(schema.CLUBS, [["GS", "G", "GAL", "Istanbul", "#A90432", "RAMS"]], headers=headers),
        schema.CLUBS,
    )
    assert not result.ok
    assert "stadium" in result.errors[0].message


def test_errors_carry_the_spreadsheet_row_number(make_sheet):
    rows = [
        ["GS-1", "Fernando Muslera", "Muslera", "GS", "GK", 8.5, None, None, None, None],
        ["GS-2", "Bad Position", "Bad", "GS", "SWEEPER", 5.0, None, None, None, None],
    ]
    result = read_sheet(make_sheet(schema.PLAYERS, rows), schema.PLAYERS)
    assert not result.ok
    assert result.errors[0].row == 3  # header is row 1, first data row is 2
    assert result.errors[0].field == "position"


def test_blank_rows_are_skipped(make_sheet):
    rows = [CLUB_ROWS[0], [None, None, None, None, None], CLUB_ROWS[1]]
    result = read_sheet(make_sheet(schema.CLUBS, rows), schema.CLUBS)
    assert result.ok
    assert len(result.rows) == 2


def test_optional_player_fields_default_sensibly(make_sheet):
    rows = [["GS-1", "Fernando Muslera", "Muslera", "gs", "gk", None, None, None, None, None]]
    result = read_sheet(make_sheet(schema.PLAYERS, rows), schema.PLAYERS)
    assert result.ok
    player = result.rows[0][1]
    assert player.position is Position.GK
    assert player.status is PlayerStatus.ACTIVE
    assert player.price == 0.0


def test_missing_file_reports_cleanly(tmp_path):
    result = read_sheet(tmp_path / "nope.xlsx", schema.CLUBS)
    assert not result.ok
    assert "file not found" in result.errors[0].message


def test_fixture_rejects_team_playing_itself(make_sheet):
    rows = [["GW1-GS-GS", 1, "2025-08-08 18:00", "GS", "GS", None, None, None]]
    result = read_sheet(make_sheet(schema.FIXTURES, rows), schema.FIXTURES)
    assert not result.ok
    assert "must differ" in result.errors[0].message


def test_final_fixture_requires_scores(make_sheet):
    rows = [["GW1-GS-FB", 1, "2025-08-08 18:00", "GS", "FB", "final", None, None]]
    result = read_sheet(make_sheet(schema.FIXTURES, rows), schema.FIXTURES)
    assert not result.ok
    assert "home_score" in result.errors[0].message
