# Fantasy Süper Lig — Phase 1 Development Plan

A Yahoo Fantasy–style football game for the Turkish Süper Lig. Phase 1 runs locally,
is fed by Excel sheets, and uses a **snake draft**.

---

## 1. Decisions locked in

| Decision | Choice | Notes |
|---|---|---|
| Format | Draft league, head-to-head | True Yahoo model: each player is owned by exactly one team in a league |
| Draft type | **Snake** | Order reverses each round. Auction mode deferred to a later phase |
| Player price | Metadata only in Phase 1 | Displayed in the player pool, used for default rankings and as the seam for a future auction draft. Does **not** gate acquisition |
| Data source | Excel sheets you maintain | Behind a `DataSource` interface so a live API drops in later without touching the rest of the app |
| Stack | Python 3.14 + FastAPI + SQLModel + SQLite + Jinja2 + HTMX | Python already installed; no Node, no Docker needed |
| Deployment | Localhost only | SQLite file, cookie sessions, no email |
| League | Turkish Süper Lig, one season | 18 clubs, 34 gameweeks |

### Explicit non-goals for Phase 1

Not built now, but the data model must not block them: live API ingest, auction
drafts, public hosting, mobile app, payments, chat, multi-sport, keeper/dynasty
leagues, email notifications, password reset.

---

## 2. Stack and why

- **FastAPI** — async, great for the draft room's server-sent events, and the same
  app can later expose a JSON API for a mobile client.
- **SQLModel** (SQLAlchemy + Pydantic) — one class defines both the table and the
  validation schema. Less duplication while the model is still churning.
- **SQLite** — a single file you can copy, delete, and reseed freely. Migrating to
  Postgres later is a connection-string change plus an Alembic run.
- **Alembic** — from day one. The schema will change a lot; you do not want to be
  reseeding by hand.
- **Jinja2 + HTMX** — server-rendered HTML with partial updates. The draft room needs
  live updates, and HTMX's SSE extension handles that without a JS build step.
- **Typer** — CLI for imports, seeding, scoring recomputes, and advancing gameweeks.
  Every operational action should be a command, not a button you forgot you needed.
- **pytest** — the draft engine and scoring engine must be testable with no HTTP.

---

## 3. Project structure

```
fantasy-app/
├── pyproject.toml
├── .env.example
├── README.md
├── docs/
│   └── PLAN.md
├── data/
│   ├── templates/            # blank .xlsx with correct headers — you fill these
│   └── inbox/                # you drop filled sheets here; importer reads from here
├── alembic/
├── app/
│   ├── main.py               # FastAPI app factory
│   ├── config.py             # settings from .env
│   ├── db.py                 # engine, session dependency
│   ├── cli.py                # typer commands
│   ├── models/
│   │   ├── catalog.py        # Season, Club, Player, Gameweek, Fixture
│   │   ├── identity.py       # User
│   │   ├── league.py         # FantasyLeague, FantasyTeam, LeagueSettings
│   │   ├── draft.py          # Draft, DraftSlot, DraftPick, PlayerQueue
│   │   ├── roster.py         # RosterSlot, Lineup, LineupSlot
│   │   ├── stats.py          # PlayerGameweekStat
│   │   ├── scoring.py        # ScoringProfile, ScoringRule, PlayerGameweekScore
│   │   ├── matchup.py        # Matchup, StandingsRow
│   │   └── transaction.py    # Transaction, WaiverClaim, TradeOffer
│   ├── ingest/
│   │   ├── protocol.py       # DataSource interface  ← the Phase 2 seam
│   │   ├── rows.py           # pydantic row schemas, shared by all sources
│   │   ├── excel/
│   │   │   ├── reader.py     # openpyxl → dicts
│   │   │   └── source.py     # ExcelDataSource(DataSource)
│   │   ├── api/              # Phase 2: ApiDataSource(DataSource)
│   │   └── importer.py       # upsert logic, source-agnostic
│   ├── services/
│   │   ├── auth.py
│   │   ├── draft_engine.py   # pure state machine, no HTTP
│   │   ├── scoring_engine.py # pure function: stats + rules → points
│   │   ├── lineup.py         # legality, locking
│   │   ├── waivers.py
│   │   └── standings.py
│   └── web/
│       ├── routes/           # auth, leagues, players, draft, team, matchups
│       ├── templates/
│       └── static/
└── tests/
```

---

## 4. Domain model

### 4.1 Catalog (fed by Excel — this is the "real world")

- **Season** — `2025-26`, start/end dates.
- **Club** — 18 Süper Lig clubs. Stable `club_code`.
- **Player** — belongs to a club, has `position` (GK/DEF/MID/FWD), `price`, `status`.
  Stable `player_code`.
- **Gameweek** — 1..34, with `deadline_utc` (kickoff of the first fixture).
- **Fixture** — home club, away club, gameweek, kickoff, score, status.

### 4.2 Identity

- **User** — email, argon2 password hash, display name. No email verification.

### 4.3 Fantasy layer

- **FantasyLeague** — name, season, join code, commissioner, settings blob
  (team count, roster shape, scoring profile, draft type, waiver mode).
- **FantasyTeam** — one per user per league. Name, logo emoji, `is_bot` flag.
- **RosterSlot** — *temporal ownership*: `(team, player, from_gameweek, to_gameweek)`.
  This is the single most important modelling decision. Ownership changes mid-season
  via waivers and trades, and standings must stay correct for past weeks. Never
  delete a roster row — close it by setting `to_gameweek`.
- **Lineup / LineupSlot** — per team per gameweek: who starts, who benches.
- **Matchup** — head-to-head pairing per gameweek per league.

### 4.4 Stats and scoring

- **PlayerGameweekStat** — raw, immutable facts from the sheets. Goals, assists,
  minutes, saves, cards, etc.
- **ScoringProfile / ScoringRule** — configurable points per stat per position.
- **PlayerGameweekScore** — derived. Always recomputable from stat + rules.

> **Rule:** raw stats are the source of truth; scores are always derived and can be
> thrown away and rebuilt. If you ever hand-edit a score, you have a bug.

### 4.5 Provenance columns (every catalog + stat table)

`source` (`excel` / `api`), `source_ref` (filename or endpoint), `ingested_at`.
Costs nothing now, saves you when Phase 2 data disagrees with Phase 1 data.

---

## 5. Excel ingest contract

Four sheet types. Blank templates with the exact headers get generated into
`data/templates/` by `fantasy init-templates`. The header row is the contract —
the importer validates it and refuses to guess.

**`clubs.xlsx`**
```
club_code | name | short_name | city | primary_color
```

**`players.xlsx`**
```
player_code | full_name | display_name | club_code | position | price |
birth_date | nationality | shirt_number | status
```
`position` ∈ `GK|DEF|MID|FWD` · `status` ∈ `active|injured|suspended|unavailable`

**`fixtures.xlsx`**
```
fixture_code | gameweek | kickoff_utc | home_club_code | away_club_code |
status | home_score | away_score
```

**`stats_gw{n}.xlsx`** — one file per gameweek, your weekly results feed
```
fixture_code | player_code | minutes | goals | assists | shots | key_passes |
saves | pens_saved | pens_missed | goals_conceded | own_goals |
yellow_cards | red_cards | motm
```

### Importer rules

1. **Idempotent.** Upsert keyed on `*_code`. Running the same file twice changes nothing.
2. **`--dry-run` by default in the plan, and always available.** Prints an add/update/skip
   summary and a validation error report; writes nothing.
3. **Fail loudly on unknown references.** A `player_code` pointing at a nonexistent club
   is an error, not a silent null.
4. **Whole-file transaction.** Either the sheet imports or nothing does.
5. **Report row numbers** in errors so you can fix the spreadsheet directly.

Commands:
```bash
fantasy init-templates
fantasy import clubs data/inbox/clubs.xlsx --dry-run
fantasy import players data/inbox/players.xlsx
fantasy import stats data/inbox/stats_gw7.xlsx --gameweek 7
```

---

## 6. Scoring rules (starting profile — all configurable)

| Event | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Played 1–59 min | 1 | 1 | 1 | 1 |
| Played 60+ min | 2 | 2 | 2 | 2 |
| Goal | 10 | 6 | 5 | 4 |
| Assist | 3 | 3 | 3 | 3 |
| Clean sheet (60+ min) | 5 | 4 | 1 | 0 |
| Every 3 saves | 1 | — | — | — |
| Penalty saved | 5 | — | — | — |
| Penalty missed | −2 | −2 | −2 | −2 |
| Every 2 goals conceded | −1 | −1 | 0 | 0 |
| Yellow card | −1 | −1 | −1 | −1 |
| Red card | −3 | −3 | −3 | −3 |
| Own goal | −2 | −2 | −2 | −2 |

Seeded as rows in `ScoringRule`, not constants in code. `fantasy recompute-scores`
rebuilds every historical score after a rule change.

---

## 7. Roster shape and snake draft

### Roster (league setting, these are the defaults)

| Slot | Count |
|---|---|
| GK | 1 |
| DEF | 4 |
| MID | 4 |
| FWD | 2 |
| Bench | 4 |
| **Total** | **15** |

Positional maximums enforced at draft time so nobody ends up unable to field a legal XI.

### Snake draft mechanics

- League size 8–12 (default 10). Rounds = roster size (15).
- Draft order set randomly (or manually by the commissioner) before the draft.
- Order reverses every round: `1→10`, then `10→1`, then `1→10`, …
- **Per-pick timer** (default 60s), server-authoritative. Nobody's clock depends on
  their browser being open.
- **Pre-draft queue** — each manager ranks players ahead of time. On timeout, autopick
  takes the highest-ranked available player from their queue that fits a legal open
  slot; if the queue is empty, it falls back to best available by price then position need.
- Managers can toggle **autodraft** on and let the queue run the whole thing.
- Drafted players are locked league-wide — a player taken is off everyone's board.

### Implementation shape

The draft engine is a **pure state machine**: `(draft_state, event) → (new_state, effects)`.
Events are `MakePick`, `TimerExpired`, `ToggleAutodraft`, `UpdateQueue`. It knows nothing
about HTTP or SSE. Build and fully unit-test it before writing a single line of draft UI —
this is the part most likely to eat your schedule.

The web layer then: persists state, broadcasts changes over SSE to everyone in the room,
and runs one async timer task per active draft.

**Bot managers** are essential here. You are building this alone on localhost — without
bots you cannot test a 10-team draft. A bot is just a `FantasyTeam` with `is_bot=True`
that is permanently on autodraft.

---

## 8. Weekly lifecycle

```
Gameweek N opens
   ↓
Waivers process (Wednesday run)          fantasy run-waivers --gameweek N
   ↓
Free-agent adds / drops / trades open
   ↓
Managers set lineups
   ↓
DEADLINE = first kickoff of GW N         lineups lock
   ↓
Matches played
   ↓
You fill stats_gw{N}.xlsx and import     fantasy import stats ... --gameweek N
   ↓
Scores computed, matchups resolved       fantasy score-gameweek N
   ↓
Standings updated → Gameweek N+1 opens   fantasy advance-gameweek
```

Every step is a CLI command. Nothing depends on a cron job or a running server in Phase 1.

---

## 9. Milestones

Estimates assume focused solo work.

| # | Milestone | Est. | Done when |
|---|---|---|---|
| ~~**M0**~~ | ~~Skeleton~~ | ~~0.5d~~ | **✅ done** — uvicorn serves the catalog status page, SQLite + Alembic wired, 29 tests pass, `fantasy --help` runs |
| ~~**M1**~~ | ~~Catalog + Excel ingest~~ | ~~2d~~ | **✅ done** — 18 clubs imported; verified against a synthetic full season (306 fixtures, 34 gameweeks auto-created). Re-import is a no-op, bad rows produce row-numbered errors and write nothing |
| **M2** | Auth + app shell | 1d | Register, log in, log out. Base layout with nav. Player pool page: filter by club/position/status, sort by price, paginated |
| **M3** | Leagues + teams | 1d | Create a league with settings, join by code, add bot managers, see "My Team" |
| **M4** | **Draft engine (core)** | 2d | State machine passes unit tests: snake order, positional limits, timeouts, autopick, queue handling, full 10×15 draft simulated headlessly with zero illegal rosters |
| **M5** | Draft room (UI) | 1.5d | Live board over SSE, pick clock, queue drag-ordering, available-player filter. A real draft completes in the browser against 9 bots |
| **M6** | Rosters + lineups | 1.5d | Set starters/bench per gameweek, illegal formations rejected, lineup locks at the deadline, historical lineups preserved |
| **M7** | Stats ingest + scoring | 2d | Import a gameweek's stats, see per-player and per-team points. `recompute-scores` is idempotent. Editing a scoring rule and recomputing updates all history |
| **M8** | Matchups + standings | 1.5d | Round-robin schedule generated at draft completion, H2H results per gameweek, standings with W/L/D and points-for tiebreak |
| **M9** | Transactions | 2d | Free-agent add/drop with roster-legality checks, waiver claims by reverse standings, 1-for-1 trade offer/accept/reject. All ownership changes respect the temporal `RosterSlot` model |
| **M10** | Demo seed + docs | 1d | `fantasy seed-demo` builds a full league mid-season from fake data. README explains the weekly loop |

**Total: ~16 working days.**

### Suggested build order note

M4 before M5 is deliberate. Do not build the draft UI until the engine is green in tests.
Likewise M7's scoring engine should be unit-tested against a handful of hand-computed
players before you render a single points table.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Draft room is the hardest part** and is easy to underestimate | Pure state machine, tested headlessly first. UI is a thin projection over it |
| **Player identity instability** — your sheets must use the same `player_code` every week, forever | Decide the code scheme once (e.g. `TR-{club}-{surname}-{n}`) and never recycle. This is also what makes the Phase 2 API swap survivable — you will need a mapping table |
| **Excel data quality** — one typo'd club code corrupts a gameweek | Hard validation, dry-run, whole-file transactions, row-numbered errors |
| **Weekly stat entry is manual and tedious** — 300+ rows per gameweek | Accept it for Phase 1; it is the point of the phase. Keep the sheet narrow, and treat "this is annoying" as the signal that tells you when Phase 2 is worth it |
| **Timezones** | Store UTC everywhere, display Europe/Istanbul. Süper Lig kickoffs cross DST boundaries |
| **Scoring rule changes mid-season** | Scores are always derived; never hand-edited. `recompute-scores` is the only way scores change |
| **Scope creep toward Yahoo feature parity** | The non-goals list in §1 is the contract. Chat, mobile, and public hosting are all Phase 3+ |

---

## 11. The Phase 2 seam (live API)

Everything ingest-related goes through one interface:

```python
class DataSource(Protocol):
    def fetch_clubs(self, season: str) -> list[ClubRow]: ...
    def fetch_players(self, season: str) -> list[PlayerRow]: ...
    def fetch_fixtures(self, season: str) -> list[FixtureRow]: ...
    def fetch_gameweek_stats(self, season: str, gw: int) -> list[StatRow]: ...
```

`ExcelDataSource` implements it in Phase 1. `ApiDataSource` implements it in Phase 2.
`importer.py` depends only on the protocol and the shared `rows.py` schemas, so the
swap touches exactly one module plus a config flag.

Do these three things now and Phase 2 becomes routine:
1. **Provenance columns** on every ingested row (§4.5).
2. **Stable external codes** that you control, with a mapping table ready for the day
   the API's ids disagree with yours.
3. **Row schemas in `rows.py`**, never inline dicts. The API must be forced to conform
   to your shape, not the other way round.

---

## 12. Open questions to answer before M3

1. League size — 10 teams default, or something else?
2. Regular season length and playoffs? 34 gameweeks is a lot of head-to-head weeks;
   a common shape is GW1–26 regular season, GW27–30 playoffs for the top 4.
3. Where do the player prices come from, and do they move during the season?
   (Static for Phase 1 is fine and much simpler.)
4. Should bench players auto-substitute when a starter records 0 minutes?
   FPL does this; Yahoo does not. Yahoo behaviour is simpler — recommend deferring.
