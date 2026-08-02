from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.web.deps import WEB_DIR, LoginRequired, flash, redirect
from app.web.routes import auth, home, players


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Fantasy Süper Lig", debug=settings.debug)

    # Signed cookie sessions. Adequate while the app is local-only; if this is ever
    # hosted, revisit with a server-side store and https_only=True.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        max_age=60 * 60 * 24 * 30,
    )

    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    app.include_router(home.router)
    app.include_router(auth.router)
    app.include_router(players.router)

    @app.exception_handler(LoginRequired)
    def _login_required(request: Request, exc: LoginRequired):
        flash(request, "Please sign in to continue.", "info")
        return redirect(f"/login?next={exc.next_url}")

    return app


app = create_app()
