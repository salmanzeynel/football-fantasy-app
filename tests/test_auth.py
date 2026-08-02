"""M2 acceptance: register, sign in, sign out, and the pages that depend on it."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import create_app
from app.services import auth

GOOD = {
    "email": "manager@example.com",
    "display_name": "Zeynel",
    "password": "correct-horse",
    "password_confirm": "correct-horse",
}


@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


# ------------------------------------------------------------------ service layer


def test_password_is_hashed_not_stored(session):
    user = auth.register(session, email="a@b.com", password="hunter2!!", display_name="A")
    assert user.password_hash != "hunter2!!"
    assert auth.verify_password(user.password_hash, "hunter2!!")
    assert not auth.verify_password(user.password_hash, "wrong")


def test_email_is_normalised(session):
    auth.register(session, email="  MiXeD@Case.COM ", password="hunter2!!", display_name="A")
    assert auth.get_by_email(session, "mixed@case.com") is not None


def test_duplicate_email_is_rejected(session):
    auth.register(session, email="a@b.com", password="hunter2!!", display_name="A")
    with pytest.raises(auth.AuthError, match="already exists"):
        auth.register(session, email="A@B.com", password="another1!", display_name="B")


def test_short_password_is_rejected(session):
    with pytest.raises(auth.AuthError, match="at least"):
        auth.register(session, email="a@b.com", password="short", display_name="A")


def test_authenticate_rejects_wrong_password(session):
    auth.register(session, email="a@b.com", password="hunter2!!", display_name="A")
    with pytest.raises(auth.AuthError):
        auth.authenticate(session, email="a@b.com", password="nope")


def test_authenticate_gives_nothing_away_about_unknown_emails(session):
    with pytest.raises(auth.AuthError, match="Email or password is incorrect"):
        auth.authenticate(session, email="ghost@b.com", password="whatever1")


def test_disabled_account_cannot_sign_in(session):
    user = auth.register(session, email="a@b.com", password="hunter2!!", display_name="A")
    user.is_active = False
    session.add(user)
    session.commit()
    with pytest.raises(auth.AuthError, match="disabled"):
        auth.authenticate(session, email="a@b.com", password="hunter2!!")


# -------------------------------------------------------------------- web layer


def test_register_signs_the_user_in(client):
    response = client.post("/register", data=GOOD, follow_redirects=True)
    assert response.status_code == 200
    assert "Zeynel" in response.text
    assert "Sign out" in response.text


def test_mismatched_confirmation_is_rejected(client):
    bad = {**GOOD, "password_confirm": "different"}
    response = client.post("/register", data=bad)
    assert "do not match" in response.text
    assert "Sign out" not in response.text


def test_login_logout_round_trip(client):
    client.post("/register", data=GOOD, follow_redirects=True)
    client.post("/logout", follow_redirects=True)

    anonymous = client.get("/")
    assert "Sign in" in anonymous.text

    response = client.post(
        "/login",
        data={"email": GOOD["email"], "password": GOOD["password"]},
        follow_redirects=True,
    )
    assert "Zeynel" in response.text


def test_bad_login_shows_an_error_and_stays_out(client):
    client.post("/register", data=GOOD, follow_redirects=True)
    client.post("/logout", follow_redirects=True)
    response = client.post("/login", data={"email": GOOD["email"], "password": "wrong"})
    assert "incorrect" in response.text
    assert "Sign out" not in response.text


def test_flash_message_shows_once(client):
    client.post("/register", data=GOOD, follow_redirects=True)
    assert "Welcome, Zeynel" not in client.get("/").text


def test_signed_in_user_is_bounced_off_the_login_page(client):
    client.post("/register", data=GOOD, follow_redirects=True)
    assert client.get("/login", follow_redirects=False).status_code == 303


def test_next_parameter_cannot_redirect_off_site(client):
    client.post("/register", data=GOOD, follow_redirects=True)
    client.post("/logout", follow_redirects=True)
    response = client.post(
        "/login",
        data={**{"email": GOOD["email"], "password": GOOD["password"]}, "next": "//evil.example.com"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"


def test_next_parameter_allows_internal_paths(client):
    client.post("/register", data=GOOD, follow_redirects=True)
    client.post("/logout", follow_redirects=True)
    response = client.post(
        "/login",
        data={**{"email": GOOD["email"], "password": GOOD["password"]}, "next": "/players"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/players"


def test_stale_session_for_a_deleted_user_is_dropped(client, session):
    client.post("/register", data=GOOD, follow_redirects=True)
    user = auth.get_by_email(session, GOOD["email"])
    session.delete(user)
    session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert "Sign in" in response.text
