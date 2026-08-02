from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, func, select

from app.db import get_session
from app.models.catalog import Club, Fixture, Gameweek, Player, Season
from app.models.identity import User
from app.web.deps import get_current_user, render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User | None, Depends(get_current_user)],
):
    def count(model) -> int:
        return session.exec(select(func.count()).select_from(model)).one()

    return render(
        request,
        "index.html",
        {
            "counts": [
                ("Clubs", count(Club), "/players"),
                ("Players", count(Player), "/players"),
                ("Gameweeks", count(Gameweek), None),
                ("Fixtures", count(Fixture), None),
            ],
            "season": session.exec(select(Season).where(Season.is_current)).first(),
        },
        user=user,
    )


@router.get("/healthz")
def healthz():
    return {"status": "ok"}
