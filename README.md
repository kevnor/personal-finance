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
| `server/corrections.py` | Applies the household's one-off corrections |
| `server/lib/local.py` | Reads `data/local.json` — the household's own facts |
| `db/migrations/` | Numbered SQL migrations, applied in filename order |
| `client/` | React PWA |
| `client/src/sw.js` | Service worker; its rules live in `lib/swStrategy.js` |
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

The dev server proxies `/api` to `http://127.0.0.1:8000`, so run uvicorn
alongside it (override with `PF_API_ORIGIN`). In production one FastAPI
process serves both, and the client's same-origin `/api` paths work
unchanged — which is what keeps the session cookie working with no CORS
configuration anywhere.

Every screen reads the API. There is no fixture data left in the client, and
no second copy of any rule: the category a hand-entered row gets is decided
by the same `categorise` the importer runs, and the weekly figures come from
`/api/budget` rather than being recomputed in the browser. Where the client
does aggregate — per-day bars, the Stats page — it filters exactly as the
server's `_variable_spent` does, so the two agree.

Category names are English identifiers that rules key on; the interface is
Norwegian. `GET /api/categories` serves both a `name` and a `label`, and the
client displays the label while sending the name back. Keeping the mapping
server-side is deliberate: a table in the client would go stale the moment a
category was added, and go stale silently.

## Local configuration

Some of what this app needs to categorise correctly identifies the people
using it: a card account number, an employer's name, a payment to a named
person whose purpose no rule can infer. Those are facts about one household,
not about budgeting, so they are **not** in this repository. They live in one
gitignored file beside the database — `data/local.json`, on the same volume,
for the same reason the passcode is there rather than in the database.

Everything in it is optional, and a clone with no file at all runs fine: it
categorises by the built-in rules alone and applies no corrections, which is
the right behaviour for an instance with no household attached to it yet.

```json
{
  "rules": [
    { "pattern": "til\\s*:\\s*12345678901", "category": "Credit card payment" },
    { "pattern": "giro.*acme", "category": "Employer reimbursement", "needs_review": true }
  ],
  "recategorisations": [
    { "date": "2026-07-28", "description": "<the row's exact description>",
      "amount": -166.0, "category": "Gifts" }
  ],
  "reimbursements": [
    { "date": "2026-07-30", "description": "<the row's exact description>",
      "amount": -13990.0, "expected_from": "Acme AS", "note": "employer-paid phone" }
  ]
}
```

- **`rules`** are regexes tested *before* the built-in rules and *after*
  anything taught in the UI, because they are more specific than any generic
  rule can be — an account number matches one account and nothing else.
- **`recategorisations`** and **`reimbursements`** are corrections about one
  specific payment, keyed on that row's own content rather than its id (ids
  are assigned by insertion order and mean nothing across databases). They
  are re-applied on every import and are idempotent, because a correction
  that changes no amount cannot be noticed missing by the reconciliation
  invariant.

A malformed file raises rather than being ignored: silently continuing would
mean a household's corrections quietly stop being applied, which is the
failure this arrangement exists to prevent.

## Tests

```bash
python3 -m pip install -e . pytest httpx
python3 -m pytest -q

cd client && npm test
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
- **Client tests**, under `client/src/test/`, run with vitest against a fake
  server. They cover the API wrapper's error handling, the auth gate's three
  states, the write paths — where a bug means bad data rather than a bad
  render: the sign on a hand-entered amount, a correction that teaches a
  rule, preview-before-commit on an upload — and the service worker's caching
  rules, which are the worst thing in a web app to get wrong, since a worker
  persists across reloads and keeps serving whatever it decided to keep.
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

## Offline and installation

The client is a PWA: `manifest.webmanifest` plus a service worker registered
from the root, so it installs to a home screen and opens without a browser
chrome. Both need a **secure context** — service workers only register over
HTTPS or on `localhost`. Served as `http://192.168.1.x:8000` there is no
worker and no install prompt, which is why `tailscale serve` is part of the
design rather than a nicety.

What the worker caches, and why (the rules are one pure function,
`src/lib/swStrategy.js`, with its own tests):

| Request | Strategy |
|---|---|
| Navigations | Network first, cached shell behind it — a reload works with no signal |
| `/assets/*` | Cache first; Vite content-hashes them, so a URL's bytes never change |
| `GET /api/*` | Network first, last response as fallback — this is the offline promise |
| `/api/auth/*` | Never cached: a stale `authenticated: true` would show the app to someone the server has already stopped accepting |
| Writes | Never cached, never queued |

**Reads survive going offline; writes do not.** A write queue means conflict
resolution and a sync state machine, and worse, a user who believes an
expense was recorded when it was not. The app says so rather than hiding it:
offline it shows a standing notice, and a save fails with a message instead
of appearing to work.

One consequence worth knowing: because auth state is never cached, the app
falls back to a local note (`localStorage`) to decide it may open offline.
That is not an authentication decision and cannot be used as one — it only
unlocks data already in this browser's own cache, put there by an
authenticated session on this device. Every request still goes to the server,
and a session it no longer accepts comes back 401, which clears the note and
returns to the login screen.

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

The bank fetch, deliberately deferred — see "Deferred: bank integration" in
the spec. The ingest pipeline is shaped so it lands as a fourth source.
