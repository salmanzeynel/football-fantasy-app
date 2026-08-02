# Fantasy Süper Lig

A Yahoo-style fantasy football game for the Turkish Süper Lig. Phase 1 runs locally,
is fed by Excel sheets you maintain, and uses a snake draft.

Full roadmap: [docs/PLAN.md](docs/PLAN.md).

**Status: M0–M2 complete** — project skeleton, catalog models, Excel ingest, accounts,
and the player pool. Leagues, the draft, and scoring are still ahead (M3 onward).

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Optionally `cp .env.example .env` and set a real `SECRET_KEY`. The defaults work as-is
for local use.

## Getting data in

Generate blank sheets with the exact headers the importer expects:

```bash
.venv/bin/fantasy init-templates
```

That writes `clubs.xlsx`, `players.xlsx`, `fixtures.xlsx` and `stats_gw1.xlsx` into
`data/templates/`. Each has a `_notes` tab documenting every column. Fill them in, save
the completed files to `data/inbox/`, then:

```bash
.venv/bin/fantasy import clubs --dry-run
.venv/bin/fantasy import clubs
.venv/bin/fantasy import players
.venv/bin/fantasy import fixtures
```

`data/inbox/clubs.xlsx` already contains the 18 Süper Lig clubs as a starting point —
**check the list against the current season before you rely on it.**

### Rules the importer follows

- **Idempotent.** Records are matched on their `*_code` column, so re-running an import
  is an upsert, never an append. Running the same file twice reports everything unchanged.
- **`--dry-run`** does the entire import, reports exactly what would happen, and rolls
  it back.
- **Whole-file transaction.** If any row fails validation, nothing is written — valid
  rows in the same file do not sneak through.
- **Errors name the spreadsheet row**, so you can fix the file directly:

  ```
  ✗ players: 3 problem(s) - nothing was written.
    players row 4 [position]: Input should be 'GK', 'DEF', 'MID' or 'FWD'
    players row 5 [club_code]: unknown club 'TOTTENHAM' - import clubs.xlsx first
  ```

- **The header row is the contract.** A missing, renamed, or extra column is rejected
  rather than guessed at.
- **Codes are stored upper-case**, so `gs` and `GS` can never become two clubs.

Gameweeks are created automatically from the fixture list, and each gameweek's deadline
is set to its first kickoff — that is when lineups will lock.

## Running the app

```bash
.venv/bin/fantasy serve
```

Then open http://127.0.0.1:8000 and create an account — the first one you register is
just a normal account; there is no admin role yet.

Pages so far:

| Path | What it does |
|---|---|
| `/` | Catalog status — what has been imported |
| `/players` | Player pool: search, filter by club/position/status, sortable columns, paged |
| `/register`, `/login` | Accounts |

Passwords are hashed with argon2id and sessions are signed cookies. There is **no
password reset** — the app is local-only and has no email. If you lock yourself out,
delete the row from the `user` table and register again.

Filtering and sorting are plain query parameters, so any view of the player pool is a
shareable URL and the page works with JavaScript disabled.

## Tests

```bash
.venv/bin/pytest
```

## Schema changes

```bash
.venv/bin/alembic revision --autogenerate -m "what changed"
.venv/bin/alembic upgrade head
```

New model modules must be imported in `app/models/__init__.py` or autogenerate will not
see them.

## Layout

| Path | What lives there |
|---|---|
| `app/models/` | SQLModel tables. `catalog.py` is football data, `identity.py` is accounts |
| `app/services/` | Logic with no web dependencies — `auth.py` today |
| `app/web/deps.py` | Session helpers, `get_current_user` / `require_user`, template rendering |
| `app/ingest/rows.py` | Validated row schemas — the shape every data source must produce |
| `app/ingest/protocol.py` | `DataSource` — the seam a live API plugs into in phase 2 |
| `app/ingest/excel/` | Spreadsheet reader, header specs, template generator |
| `app/ingest/importer.py` | Rows → database. Knows nothing about Excel |
| `app/cli.py` | Every operational action |
| `app/web/` | FastAPI routes, Jinja templates, CSS |

## Time

Everything is stored in UTC, including `kickoff_utc` in the fixtures sheet — enter UTC
there, not Istanbul time. Display conversion to Europe/Istanbul happens in the UI.
