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
| `server/cli.py` | `import`, `reconcile` and `budget` commands |
| `server/lib/ingest/` | Statement readers; one module per source format |
| `server/lib/categorise.py` | Pure: description text in, category out |
| `server/lib/derive.py` | Splits an itemised row (a loan term) into its parts |
| `server/lib/budget.py` | The weekly-envelope engine |
| `server/lib/store.py` | Connections, migrations, transaction writes |
| `server/corrections.py` | One-off account-holder facts no rule can express |
| `db/migrations/` | Numbered SQL migrations, applied in filename order |
| `client/` | React PWA (currently running on fixture data) |
| `data/` | The live database — gitignored |
| `input/` | Drop-zone for statements — gitignored |

## Running it

Python 3.11 or newer. No runtime dependencies.

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

### The client

```bash
cd client
npm install
npm run dev          # http://localhost:5173
```

The client currently renders `src/lib/mockData.js`. There is no HTTP API yet
— the spec's `server/app.py` and `server/routes/` are unbuilt — so nothing
connects it to the pipeline above.

## Tests

```bash
python3 -m pip install pytest
python3 -m pytest -q
```

The suite is in two parts:

- **Structural tests**, which run everywhere. They use synthetic statements
  built by `server/test/fixtures/statements.py`, which writes real `.xlsx`
  files at test time from a readable table of rows. This is what covers the
  ingest invariants the spec calls the highest-value tests in the project:
  re-importing a file is a no-op, overlapping periods do not duplicate, two
  identical same-day purchases are both retained, and identity is scoped per
  account.
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

## Not built yet

The spec's v1 scope that has no code behind it: the FastAPI backend and its
routes, passcode auth, the client's data layer, service worker and
installable-PWA icons, and Docker packaging.
