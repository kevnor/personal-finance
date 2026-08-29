# personal-finance

A weekly-envelope budgeting app for one household. Bank and credit-card
statements are imported into SQLite, categorised by rule, and turned into a
daily spending allowance.

The design lives in
[`docs/superpowers/specs/2026-08-22-personal-finance-app-design.md`](docs/superpowers/specs/2026-08-22-personal-finance-app-design.md);
the data itself — where it comes from, what the columns mean, and why the
categorisation rules are shaped the way they are — is documented in
[`db/README.md`](db/README.md).

## Layout

| Path | What it is |
|---|---|
| `server/app.py` | FastAPI app: JSON API plus the built client |
| `server/routes/` | One module per resource |
| `server/security.py` | Passcode, sessions, rate limit |
| `server/settings.py` | Paths and timezone, from the environment |
| `server/cli.py` | `import`, `reconcile` and `budget` commands |
| `server/lib/importer.py` | The import step the CLI and API share |
| `server/lib/ingest/` | Statement readers; one module per source format |
| `server/lib/categorise.py` | Pure: description text in, category out |
| `server/lib/derive.py` | Splits an itemised row (a loan term) into its parts |
| `server/lib/budget.py` | The weekly-envelope engine |
| `server/lib/store.py` | Connections, migrations, transaction writes |
| `server/corrections.py` | One-off account-holder facts no rule can express |
| `db/migrations/` | Numbered SQL migrations, applied in filename order |
| `client/` | React PWA (currently running on fixture data) |
| `docker/` | Dockerfile and compose file |
| `data/` | The live database — gitignored |
| `input/` | Drop-zone for statements — gitignored |

## Running it

Python 3.11 or newer. The CLI below needs nothing installed — ingest,
categorisation and the budget engine are pure stdlib. The HTTP server has
dependencies; see "The server".

```bash
# Drop the statement exports into input/, then:
python3 -m server.cli import

# Report an existing database without touching it:
python3 -m server.cli reconcile

# This week's envelope and today's allowance:
python3 -m server.cli budget
python3 -m server.cli budget --date 2026-07-15
```

`import` is additive and idempotent: re-running it, or re-importing a
statement whose period overlaps one already loaded, inserts nothing new. Row
identity is a content fingerprint plus an occurrence index, so a re-export
with the rows reordered is recognised, while two genuinely separate
same-day purchases of the same amount are both kept.

`reconcile` and `budget` open the database read-only, so their promise not to
write is enforced by SQLite rather than by good intentions.

### The server

```bash
pip install -e .
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

Or with Docker, which builds the client and serves it from the same process:

```bash
docker compose -f docker/compose.yaml up --build
```

On first run there is no passcode. `GET /api/auth/status` reports
`configured: false`, and `POST /api/auth/passcode` sets one — that endpoint
closes permanently the moment a passcode exists, so an instance is claimed
once. Everything under `/api` except the four auth endpoints requires the
session cookie it hands back.

| Route | What it does |
|---|---|
| `GET /api/budget` | Today's allowance, the week's envelope, and the pools behind them |
| `GET`/`PUT /api/budget/config` | Savings target, income mode, week start — versioned |
| `GET /api/transactions` | History and, with `needs_review=true`, the review queue |
| `POST /api/transactions` | Hand entry, categorised by the same rules as an import |
| `POST /api/transactions/bulk` | Programmatic entry; all-or-nothing |
| `PATCH /api/transactions/{id}` | Recategorise, override treatment, annotate; `teach` writes a merchant rule |
| `GET`/`PATCH /api/categories` | Per-category budget treatment |
| `GET`/`POST /api/reimbursements` | What is owed, and settling it |
| `POST /api/imports/preview` | What uploading this statement would do — writes nothing |
| `POST /api/imports` | Commit the upload |

Interactive docs at `/docs`, schema at `/openapi.json`.

Configuration is environment variables, all optional: `PF_DATA_DIR`,
`PF_DB_PATH`, `PF_PASSCODE_FILE`, `PF_STATIC_DIR`, `PF_MIGRATIONS_DIR`,
`PF_TIMEZONE` (default `Europe/Oslo`), and `PF_HTTPS_ONLY` — set that last
one only when something in front terminates TLS, since a `Secure` cookie sent
over plain HTTP is dropped by the browser and login then fails to stick.

### The client

```bash
cd client
npm install
npm run dev          # http://localhost:5173
```

The client still renders `src/lib/mockData.js`; wiring it to the API above is
the next piece of work.

## Tests

```bash
python3 -m pip install -e . pytest httpx
python3 -m pytest -q
```

The suite is in three parts:

- **Structural tests**, which run everywhere. They use synthetic statements
  built by `server/test/fixtures/statements.py`, which writes real `.xlsx`
  files at test time from a readable table of rows. This is what covers the
  ingest invariants the spec calls the highest-value tests in the project:
  re-importing a file is a no-op, overlapping periods do not duplicate, two
  identical same-day purchases are both retained, and identity is scoped per
  account.
- **API contract tests**, driven through `fastapi.testclient`. The load-
  bearing one enumerates every route the app publishes and asserts each is
  either listed as public by design or answers 401 without a session, so a
  route added later is covered without anyone remembering to add it here.
- **Real-data tests**, which assert this dataset's own figures — 181 rows,
  net 14 084,24, the 48 counterparty values, the −13 288,75 loan term. The
  statements are gitignored, so these skip unless `input/` is populated.
  `pytest -rs` lists what skipped and why.

A golden-file regression suite (`server/test/fixtures/categorisation.json`)
pins the categorisation of every real transaction description. Because
`categorise.py` is pure, it needs no database and no I/O.

## Migrations

Migrations are applied in filename order and recorded by name with a content
checksum. Editing an applied migration is refused: it would reach a freshly
built database and never reach an existing one, and the two would diverge
silently. Add a new migration instead.

Numbers must stay contiguous — a gap is the same divergence hazard, since
migrations are skipped by name but ordered by filename. `004_reserved.sql`
holds a slot that was skipped during development; a test enforces the rule.

## Security

One passcode, argon2-hashed, in a file on the data volume beside the database
rather than inside it — so a database restored from backup does not bring an
old passcode with it. Sessions are stateless signed cookies (httpOnly,
SameSite=Lax, `Secure` when `PF_HTTPS_ONLY` is set, 30 days). Login is
rate-limited per client address.

Stated plainly, unchanged from the spec: this stops a guest's laptop or an
IoT device on the same wifi from browsing the user's finances. It is not
hardening against a determined attacker already inside the network — the
network boundary does the real work. `logout` clears the cookie rather than
revoking the token; to revoke every session, delete the credentials file and
set a new passcode, which rotates the signing secret.

## Not built yet

The client's data layer (it still renders fixture data), the service worker
and installable-PWA icons, and the deferred bank fetch.
