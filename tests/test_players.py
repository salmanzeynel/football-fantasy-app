"""M2 acceptance: the player pool filters, sorts and pages."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import create_app
from app.models.catalog import Club, Player
from app.models.enums import PlayerStatus, Position
from app.web.routes.players import PER_PAGE


@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


@pytest.fixture
def squad(session):
    """Named players in two clubs, plus a filler club big enough to force a second page.

    The filler lives in its own club so that filtering by GS or FB returns a small,
    predictable set - otherwise a cheap filler squad swamps the price-sort assertions.
    """
    gs = Club(club_code="GS", name="Galatasaray SK", short_name="GAL", primary_color="#A90432")
    fb = Club(club_code="FB", name="Fenerbahçe SK", short_name="FEN")
    filler_club = Club(club_code="ZZZ", name="Filler FK", short_name="ZZZ")
    session.add(gs)
    session.add(fb)
    session.add(filler_club)
    session.commit()

    named = [
        Player(player_code="GS-OSIMHEN", full_name="Victor Osimhen", display_name="Osimhen",
               club_id=gs.id, position=Position.FWD, price=12.0),
        Player(player_code="GS-MUSLERA", full_name="Fernando Muslera", display_name="Muslera",
               club_id=gs.id, position=Position.GK, price=6.0),
        Player(player_code="FB-TADIC", full_name="Dušan Tadić", display_name="Tadić",
               club_id=fb.id, position=Position.MID, price=9.0),
        Player(player_code="FB-HURT", full_name="Injured Person", display_name="Hurt",
               club_id=fb.id, position=Position.DEF, price=4.0, status=PlayerStatus.INJURED),
    ]
    filler = [
        Player(player_code=f"ZZZ-F{i}", full_name=f"Filler {i}", display_name=f"Filler{i}",
               club_id=filler_club.id, position=Position.MID, price=1.0 + i * 0.1)
        for i in range(PER_PAGE + 2)
    ]
    for player in named + filler:
        session.add(player)
    session.commit()
    return {"gs": gs, "fb": fb, "named": named}


def test_empty_pool_explains_how_to_fill_it(client):
    response = client.get("/players")
    assert response.status_code == 200
    assert "No players imported yet" in response.text
    assert "fantasy import players" in response.text


def test_lists_players(client, squad):
    body = client.get("/players?sort=price&direction=desc").text
    assert "Osimhen" in body
    assert "Tadić" in body


def test_filter_by_club(client, squad):
    body = client.get("/players?club=FB").text
    assert "Tadić" in body
    assert "Osimhen" not in body


def test_filter_by_position(client, squad):
    body = client.get("/players?position=GK").text
    assert "Muslera" in body
    assert "Osimhen" not in body


def test_filter_by_status(client, squad):
    body = client.get("/players?status=injured").text
    assert "Hurt" in body
    assert "Osimhen" not in body


def test_search_matches_full_name_not_just_display_name(client, squad):
    body = client.get("/players?q=victor").text
    assert "Osimhen" in body
    assert "Muslera" not in body


def test_filters_combine(client, squad):
    body = client.get("/players?club=GS&position=FWD").text
    assert "Osimhen" in body
    assert "Muslera" not in body


def test_no_matches_offers_a_way_out(client, squad):
    body = client.get("/players?q=zzzznobody").text
    assert "No players match those filters" in body
    assert "Clear filters" in body


def test_sort_by_price_descending_puts_the_most_expensive_first(client, squad):
    body = client.get("/players?sort=price&direction=desc").text
    assert body.index("Osimhen") < body.index("Muslera")


def test_sort_direction_flips(client, squad):
    body = client.get("/players?club=GS&sort=price&direction=asc").text
    assert body.index("Muslera") < body.index("Osimhen")


def test_unknown_sort_key_falls_back_instead_of_erroring(client, squad):
    response = client.get("/players?sort=;DROP TABLE player&direction=sideways")
    assert response.status_code == 200
    assert "Osimhen" in response.text


def test_pagination_splits_the_pool(client, squad):
    first = client.get("/players?sort=name&direction=asc")
    assert "Page 1 of 2" in first.text
    assert first.text.count("<tr>") == PER_PAGE + 1  # +1 for the header row

    second = client.get("/players?sort=name&direction=asc&page=2")
    assert "Page 2 of 2" in second.text


def test_page_beyond_the_end_clamps(client, squad):
    assert "Page 2 of 2" in client.get("/players?page=99").text


def test_filters_survive_paging_and_sorting_links(client, squad):
    body = client.get("/players?club=GS&sort=name&direction=asc").text
    assert "club=GS" in body, "sort and pager links must carry the active filters"


def test_filtered_result_count_is_reported(client, squad):
    assert "of 1 player" in client.get("/players?position=GK").text
