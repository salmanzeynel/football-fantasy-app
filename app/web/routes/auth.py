from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db import get_session
from app.models.identity import User
from app.services import auth
from app.web.deps import (
    flash,
    get_current_user,
    login_user,
    logout_user,
    redirect,
    render,
)

router = APIRouter()


def _safe_next(next_url: str | None) -> str:
    """Only ever redirect within this app - never to a host an attacker supplied."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


@router.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if user:
        return redirect("/")
    return render(
        request,
        "auth/register.html",
        {"is_first_account": auth.user_count(session) == 0},
        user=user,
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    email: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_confirm: Annotated[str, Form()] = "",
):
    if password != password_confirm:
        return render(
            request,
            "auth/register.html",
            {"error": "The two passwords do not match.", "email": email, "display_name": display_name},
        )
    try:
        user = auth.register(
            session, email=email, password=password, display_name=display_name
        )
    except auth.AuthError as exc:
        return render(
            request,
            "auth/register.html",
            {"error": str(exc), "email": email, "display_name": display_name},
        )

    login_user(request, user)
    flash(request, f"Welcome, {user.display_name}.", "success")
    return redirect("/")


@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user)],
    next: str | None = None,
):
    if user:
        return redirect("/")
    return render(request, "auth/login.html", {"next": next}, user=user)


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str | None, Form()] = None,
):
    try:
        user = auth.authenticate(session, email=email, password=password)
    except auth.AuthError as exc:
        return render(
            request, "auth/login.html", {"error": str(exc), "email": email, "next": next}
        )

    login_user(request, user)
    flash(request, f"Signed in as {user.display_name}.", "success")
    return redirect(_safe_next(next))


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    flash(request, "Signed out.", "info")
    return redirect("/")
