"""Shared request dependencies and template plumbing."""

from pathlib import Path

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.db import get_session
from app.models.identity import User

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

SESSION_USER_KEY = "user_id"
FLASH_KEY = "flash"


class LoginRequired(Exception):
    """Raised by require_user; turned into a redirect by the app's exception handler."""

    def __init__(self, next_url: str) -> None:
        self.next_url = next_url


def login_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def flash(request: Request, message: str, level: str = "info") -> None:
    request.session.setdefault(FLASH_KEY, []).append({"message": message, "level": level})


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop(FLASH_KEY, [])


def get_current_user(
    request: Request, session: Session = Depends(get_session)
) -> User | None:
    """The signed-in user, or None. Use for pages that render either way."""
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        # Stale cookie - the account was deleted or disabled since sign-in.
        request.session.pop(SESSION_USER_KEY, None)
        return None
    return user


def require_user(
    request: Request, user: User | None = Depends(get_current_user)
) -> User:
    """For pages that must not render logged-out."""
    if user is None:
        raise LoginRequired(next_url=request.url.path)
    return user


def render(
    request: Request,
    template: str,
    context: dict | None = None,
    *,
    user: User | None = None,
):
    """TemplateResponse with the things every page needs already in scope.

    Flashes are popped here, so a template that renders them shows each message once.
    """
    payload = {"current_user": user, "flashes": pop_flashes(request)}
    payload.update(context or {})
    return templates.TemplateResponse(request, template, payload)


def redirect(url: str) -> RedirectResponse:
    # 303 so the browser switches to GET after a form POST.
    return RedirectResponse(url, status_code=303)
