from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, func, select

from app.config import get_settings
from app.db import get_session
from app.models.catalog import Club, Fixture, Gameweek, Player, Season

WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Fantasy Süper Lig", debug=settings.debug)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, session: Session = Depends(get_session)):
        def count(model) -> int:
            return session.exec(select(func.count()).select_from(model)).one()

        season = session.exec(select(Season).where(Season.is_current)).first()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "counts": [
                    ("Clubs", count(Club)),
                    ("Players", count(Player)),
                    ("Gameweeks", count(Gameweek)),
                    ("Fixtures", count(Fixture)),
                ],
                "season": season,
            },
        )

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()
