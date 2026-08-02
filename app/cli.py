"""Operational commands. Every action the app needs is a command, not a button.

    fantasy init-db
    fantasy init-templates
    fantasy season add --code 2025-26 --name "Süper Lig 2025-26" \
        --start 2025-08-08 --end 2026-05-24 --current
    fantasy import clubs --dry-run
    fantasy import clubs
    fantasy import players
    fantasy import fixtures
    fantasy serve
"""

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from sqlmodel import select

from app.config import BASE_DIR, INBOX_DIR, TEMPLATE_DIR
from app.db import create_all, session_scope
from app.ingest.excel.source import ExcelDataSource
from app.ingest.excel.templates import write_all_templates
from app.ingest.importer import import_clubs, import_fixtures, import_players
from app.ingest.result import ImportReport
from app.models.catalog import Season

app = typer.Typer(help="Fantasy Süper Lig admin CLI", no_args_is_help=True)
season_app = typer.Typer(help="Manage seasons", no_args_is_help=True)
import_app = typer.Typer(help="Import catalog data from spreadsheets", no_args_is_help=True)
app.add_typer(season_app, name="season")
app.add_typer(import_app, name="import")

MAX_ERRORS_SHOWN = 30


def _echo_report(report: ImportReport) -> None:
    if report.errors:
        typer.secho(
            f"\n✗ {report.sheet}: {len(report.errors)} problem(s) - nothing was written.",
            fg=typer.colors.RED,
            bold=True,
        )
        # Sorted by row so the list reads in the same order as the spreadsheet.
        ordered = sorted(report.errors, key=lambda e: (e.row is None, e.row or 0, e.field or ""))
        for err in ordered[:MAX_ERRORS_SHOWN]:
            typer.secho(f"  {err}", fg=typer.colors.RED)
        if len(ordered) > MAX_ERRORS_SHOWN:
            typer.secho(f"  ... and {len(ordered) - MAX_ERRORS_SHOWN} more", fg=typer.colors.RED)
        typer.echo("\nFix the spreadsheet and run again.")
        raise typer.Exit(code=1)

    prefix = "would create/update" if report.dry_run else "imported"
    typer.secho(
        f"\n✓ {report.sheet}: {prefix} - "
        f"{report.created} new, {report.updated} changed, {report.unchanged} unchanged "
        f"({report.total} rows)",
        fg=typer.colors.GREEN,
        bold=True,
    )
    for note in report.notes:
        typer.secho(f"  · {note}", fg=typer.colors.BRIGHT_BLACK)


def _resolve_season(session, code: str | None) -> Season:
    if code:
        season = session.exec(select(Season).where(Season.code == code)).first()
        if season is None:
            typer.secho(f"No season with code '{code}'.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        return season
    season = session.exec(select(Season).where(Season.is_current)).first()
    if season is None:
        typer.secho(
            "No current season. Create one first:\n"
            '  fantasy season add --code 2025-26 --name "Süper Lig 2025-26" '
            "--start 2025-08-08 --end 2026-05-24 --current",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    return season


# ------------------------------------------------------------------------ setup


@app.command("init-db")
def init_db() -> None:
    """Create all tables directly (quick bootstrap; alembic is the real path)."""
    create_all()
    typer.secho("✓ tables created", fg=typer.colors.GREEN)


@app.command("init-templates")
def init_templates(
    directory: Annotated[Path, typer.Option("--dir", help="Where to write templates")] = TEMPLATE_DIR,
) -> None:
    """Write blank .xlsx templates with the exact headers the importer expects."""
    paths = write_all_templates(directory)
    typer.secho(f"✓ wrote {len(paths)} template(s) to {directory}", fg=typer.colors.GREEN)
    for path in paths:
        typer.echo(f"  {path.name}")
    typer.echo(f"\nFill them in, then save the completed files to {INBOX_DIR}")


@app.command("serve")
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = True,
) -> None:
    """Run the web app."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload, app_dir=str(BASE_DIR))


# ----------------------------------------------------------------------- season


@season_app.command("add")
def season_add(
    code: Annotated[str, typer.Option(help="e.g. 2025-26")],
    name: Annotated[str, typer.Option(help="Display name")],
    start: Annotated[str, typer.Option(help="YYYY-MM-DD")],
    end: Annotated[str, typer.Option(help="YYYY-MM-DD")],
    current: Annotated[bool, typer.Option("--current", help="Make this the active season")] = False,
) -> None:
    with session_scope() as session:
        if session.exec(select(Season).where(Season.code == code)).first():
            typer.secho(f"Season '{code}' already exists.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        if current:
            for other in session.exec(select(Season).where(Season.is_current)).all():
                other.is_current = False
        session.add(
            Season(
                code=code,
                name=name,
                start_date=date.fromisoformat(start),
                end_date=date.fromisoformat(end),
                is_current=current,
            )
        )
        session.commit()
    typer.secho(f"✓ season '{code}' created", fg=typer.colors.GREEN)


@season_app.command("list")
def season_list() -> None:
    with session_scope() as session:
        seasons = session.exec(select(Season).order_by(Season.code)).all()
        if not seasons:
            typer.echo("No seasons yet.")
            return
        for season in seasons:
            marker = "*" if season.is_current else " "
            typer.echo(f" {marker} {season.code}  {season.name}  ({season.start_date} → {season.end_date})")


# ----------------------------------------------------------------------- import


@import_app.command("clubs")
def import_clubs_cmd(
    path: Annotated[Path | None, typer.Argument(help="Defaults to data/inbox/clubs.xlsx")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and report, write nothing")] = False,
) -> None:
    """Import clubs. Run this before players or fixtures - both reference club_code."""
    source = ExcelDataSource(INBOX_DIR, {"clubs": path} if path else None)
    parse = source.fetch_clubs()
    with session_scope() as session:
        report = import_clubs(
            session, parse, source_ref=str(source.path_for("clubs")), dry_run=dry_run
        )
    _echo_report(report)


@import_app.command("players")
def import_players_cmd(
    path: Annotated[Path | None, typer.Argument(help="Defaults to data/inbox/players.xlsx")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and report, write nothing")] = False,
) -> None:
    """Import players. Squad changes and transfers are applied by re-running this."""
    source = ExcelDataSource(INBOX_DIR, {"players": path} if path else None)
    parse = source.fetch_players()
    with session_scope() as session:
        report = import_players(
            session, parse, source_ref=str(source.path_for("players")), dry_run=dry_run
        )
    _echo_report(report)


@import_app.command("fixtures")
def import_fixtures_cmd(
    path: Annotated[Path | None, typer.Argument(help="Defaults to data/inbox/fixtures.xlsx")] = None,
    season: Annotated[str | None, typer.Option(help="Season code; defaults to the current season")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and report, write nothing")] = False,
) -> None:
    """Import fixtures. Creates gameweeks and sets each deadline to its first kickoff."""
    source = ExcelDataSource(INBOX_DIR, {"fixtures": path} if path else None)
    parse = source.fetch_fixtures()
    with session_scope() as session:
        target = _resolve_season(session, season)
        report = import_fixtures(
            session,
            parse,
            season=target,
            source_ref=str(source.path_for("fixtures")),
            dry_run=dry_run,
        )
    _echo_report(report)


@import_app.command("stats")
def import_stats_cmd(
    gameweek: Annotated[int, typer.Option("--gameweek", "-g")],
    path: Annotated[Path | None, typer.Argument(help="Defaults to data/inbox/stats_gw{n}.xlsx")] = None,
) -> None:
    """Validate a gameweek stats sheet. Writing them lands with the scoring engine (M7)."""
    source = ExcelDataSource(INBOX_DIR, {"stats": path} if path else None)
    parse = source.fetch_gameweek_stats(gameweek)
    if parse.errors:
        typer.secho(f"✗ {len(parse.errors)} problem(s):", fg=typer.colors.RED, bold=True)
        for err in parse.errors[:MAX_ERRORS_SHOWN]:
            typer.secho(f"  {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(
        f"✓ {len(parse.rows)} stat row(s) validated for gameweek {gameweek}.",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        "  Not written yet - PlayerGameweekStat and the scoring engine arrive in M7.",
        fg=typer.colors.BRIGHT_BLACK,
    )


if __name__ == "__main__":
    app()
