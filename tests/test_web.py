"""M0 acceptance: the app boots and serves."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import create_app


@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_index_renders_with_an_empty_catalog(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Catalog status" in response.text
    assert "No season yet" in response.text


def test_index_shows_imported_counts(client, session, make_sheet, season):
    from app.ingest.excel import schema
    from app.ingest.excel.reader import read_sheet
    from app.ingest.importer import import_clubs

    rows = [["GS", "Galatasaray SK", "GAL", "Istanbul", "#A90432"]]
    import_clubs(session, read_sheet(make_sheet(schema.CLUBS, rows), schema.CLUBS))

    response = client.get("/")
    assert "Süper Lig 2025-26" in response.text
    assert "Clubs" in response.text
