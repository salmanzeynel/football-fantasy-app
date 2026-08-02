"""The player pool: browse everything imported from players.xlsx.

Filtering, sorting and paging are all plain GET query parameters, so the page works
with no JavaScript and every view is a shareable, bookmarkable URL. The draft room in
M4 is where live updates actually earn a JS dependency.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, func, or_, select

from app.db import get_session
from app.models.catalog import Club, Player
from app.models.enums import PlayerStatus, Position
from app.models.identity import User
from app.web.deps import get_current_user, render

router = APIRouter()

PER_PAGE = 25

# Whitelisted so the sort parameter can never reach the query builder as raw input.
SORTS: dict[str, tuple[str, object]] = {
    "price": ("Price", Player.price),
    "name": ("Name", Player.display_name),
    "position": ("Position", Player.position),
    "club": ("Club", Club.name),
}
DEFAULT_SORT = "price"


@router.get("/players", response_class=HTMLResponse)
def player_pool(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User | None, Depends(get_current_user)],
    q: str = "",
    club: str = "",
    position: str = "",
    status: str = "",
    sort: str = DEFAULT_SORT,
    direction: str = "desc",
    page: int = 1,
):
    sort = sort if sort in SORTS else DEFAULT_SORT
    direction = "asc" if direction == "asc" else "desc"
    page = max(page, 1)

    filters = []
    if q.strip():
        needle = f"%{q.strip()}%"
        filters.append(
            or_(Player.display_name.ilike(needle), Player.full_name.ilike(needle))
        )
    if club:
        filters.append(Club.club_code == club.upper())
    if position in Position.__members__:
        filters.append(Player.position == Position[position])
    if status in {s.value for s in PlayerStatus}:
        filters.append(Player.status == PlayerStatus(status))

    base = select(Player, Club).join(Club, Player.club_id == Club.id)
    counter = select(func.count()).select_from(Player).join(Club, Player.club_id == Club.id)
    for condition in filters:
        base = base.where(condition)
        counter = counter.where(condition)

    total = session.exec(counter).one()
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(page, pages)

    column = SORTS[sort][1]
    base = base.order_by(column.desc() if direction == "desc" else column.asc())
    rows = session.exec(base.offset((page - 1) * PER_PAGE).limit(PER_PAGE)).all()

    context = {
        "rows": rows,
        "clubs": session.exec(select(Club).order_by(Club.name)).all(),
        "positions": list(Position),
        "statuses": list(PlayerStatus),
        "sorts": {key: label for key, (label, _) in SORTS.items()},
        "filters": {
            "q": q,
            "club": club.upper(),
            "position": position,
            "status": status,
            "sort": sort,
            "direction": direction,
        },
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": PER_PAGE,
        "showing_from": (page - 1) * PER_PAGE + 1 if total else 0,
        "showing_to": min(page * PER_PAGE, total),
    }

    return render(request, "players/pool.html", context, user=user)
