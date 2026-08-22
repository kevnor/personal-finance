# Personal finance app — design

**Date:** 2026-08-22
**Status:** approved, ready for implementation planning

## Context

A self-hosted personal finance app for a single user, replacing the ad-hoc
spreadsheet-and-script workflow currently in `db/`. The immediate goal is a
daily and weekly spending figure derived only from *variable* spending, so
recurring commitments like the mortgage do not distort it.

The repository was empty scaffolding when this work began — directory tree
only, zero source files, and a `.git` with no objects. The only real assets
were three DNB statement exports in `input/` and the ingest and
categorisation work built during the 2026-08-22 session (`db/`).

### Prior work being carried forward

`db/` holds a working SQLite database of 181 transactions parsed from the
three statements, with rule-based categorisation, a loan splitter, and an
account-holder corrections layer. It reconciles to a net total of
**14 084,24 kr**. That logic moves into the app; it is not rewritten.

Bugs already found and fixed there, which the app must not regress:

- Row identity keyed on date + description + amount silently discarded two
  genuine same-day purchases at the same merchant (357 kr of real spending).
- `\bkino\b` and `\blading\b` failed to match `KinoTpp` / `LadingTpp`, since
  there is no word boundary between a memo and the glued-on `Tpp:` suffix.
- A memo records *what was bought*, not *why*: a payment memoed `Bok` was a
  present, not a book purchase.

## Scope

**In scope for v1:** data model, budget engine, FastAPI backend, React PWA,
manual transaction entry, xlsx statement import, bulk API for programmatic
entry, Docker packaging, passcode auth, Tailscale-based access.

**Out of scope for v1:** automatic bank fetch. Investigated during design and
deferred deliberately — see "Deferred: bank integration".

**Explicitly not building:** multi-user support, roles, registration,
offline write queue, browser E2E tests, a second database engine.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| v1 scope | Core app; bank fetch later | Bank fetch depends on an unconfirmed third-party signup; it must not gate everything else |
| Client | PWA | One codebase for phone and laptop; no app store, no build signing, no second client to keep in sync |
| Budget pool | Income − fixed − savings target | Self-adjusting: a raise or a new subscription moves the budget without manual edits |
| Period | Weekly envelope, daily as pace | Absorbs lumpy real spending (a weekly shop) without flagging a false overspend every week |
| Rollover | Resets weekly, no carry | Avoids slow drift where a frugal week silently inflates later budgets |
| Large purchases | Third bucket: `exceptional` | A 13 990 purchase against a 4 165 envelope makes a strict budget meaningless |
| Reimbursables | Own bucket, tracked as owed | A plain exclusion cannot tell you the money never came back |
| Savings | Explicit target; own-account transfers ignored | Prevents double-counting savings and keeps the weekly figure stable |
| Access | LAN + Tailscale, single passcode | Network is the real boundary; Tailscale also supplies the HTTPS the PWA needs |
| Stack | FastAPI + React + SQLite | Moves the validated categorisation engine over unchanged |
| Topology | Single container | Least that works; SQLite is one file to back up |

## Architecture

One container, multi-stage build: a Node stage compiles the React PWA to
static assets, a Python stage runs FastAPI serving both the JSON API and
those assets. SQLite lives on a mounted volume so data survives image
rebuilds.

Rejected alternatives: two containers behind nginx (CORS, compose network
and two images, for no benefit at one user); a monolith plus scheduler
worker (speculative until bank fetch exists — and when it does, a cron
inside the container comes first).

The trade-off accepted is no TLS termination in-app. On Tailscale this is
largely moot, since the tailnet is already encrypted and `tailscale serve`
supplies certificates.

### Repo layout

```
personal-finance/
├─ docker/
│  ├─ Dockerfile          multi-stage: build client → python runtime
│  └─ compose.yaml        single service; volume + port binding
├─ server/
│  ├─ app.py              entrypoint, static mount, passcode middleware
│  ├─ routes/             transactions, budget, categories, imports
│  ├─ lib/
│  │  ├─ ingest/          one module per statement format
│  │  ├─ categorise.py    pure: description → category
│  │  ├─ derive.py        loan splitter and other derived rows
│  │  ├─ budget.py        envelope engine
│  │  └─ store.py         connection + migrations
│  └─ test/
├─ client/src/{pages,components,utils,test}
├─ db/                    schema.sql + numbered migrations
├─ data/                  mounted volume — transactions.db (gitignored)
└─ input/                 drop-zone for statements
```

### Refactor of the existing importer

`db/import_transactions.py` currently does five jobs in one file: xlsx
parsing, categorisation rules, the loan splitter, the corrections layer, and
database writes. Correct for a script, wrong for an app — the budget engine
needs categorisation without touching a spreadsheet, and the rules need
testing without a database. It splits along seams it already has, into
`ingest/dnb_xlsx.py`, `categorise.py`, `derive.py` and `store.py`.

`categorise.py` being pure is what makes the golden-file regression suite
cheap.

## Data model

Extends the existing schema in `db/schema.sql`. Sign convention is unchanged:
`amount > 0` is money in, `amount < 0` is money out.

**Budget treatment is orthogonal to accounting kind.** A transaction's `kind`
says what it is (expense/income/transfer); its budget treatment says whether
it touches the weekly envelope. The mortgage is unambiguously an expense yet
must not affect the daily figure. Conflating the two is what makes budget
apps confusing.

### `categories` — add a default treatment

```sql
budget_treatment TEXT NOT NULL DEFAULT 'variable'
    CHECK (budget_treatment IN ('fixed','variable','exceptional'))
```

- `fixed` — mortgage interest and fees, student loan, insurance,
  electricity, gym, subscriptions
- `exceptional` — home & furniture, sports & outdoor, memberships
- `variable` — everything else (groceries, cafes, restaurants, transport,
  health, personal care, entertainment, accommodation, gifts, clothing)

Clothing & shoes is `variable` in v1 but is a plausible `exceptional`; it is
a per-category setting the user can change from Settings, so this needs no
code change.

### `transactions` — add a per-transaction override

```sql
budget_override TEXT NULL
    CHECK (budget_override IN ('fixed','variable','exceptional','reimbursable','ignore')),
origin TEXT NOT NULL DEFAULT 'import'
    CHECK (origin IN ('manual','import','bank','derived')),
fingerprint TEXT NOT NULL,
occurrence INTEGER NOT NULL DEFAULT 1
```

Effective treatment is `COALESCE(budget_override, category.budget_treatment)`.
Category defaults alone are provably insufficient: the 13 990 employer-paid
phone sits in Home & furniture, which is correct for reporting, while
`budget_override = 'reimbursable'` keeps it out of the envelope.

`origin` is needed because a manual row has no source row to point at.

### Transfers need a third axis

`is_transfer` is too blunt for budgeting, because transfers behave in three
different ways with respect to spendable cash:

```sql
-- on categories; read ONLY for categories whose kind = 'transfer'.
-- Ignored for expense and income categories.
cash_treatment TEXT NOT NULL DEFAULT 'settlement'
    CHECK (cash_treatment IN ('committed','settlement','savings'))
```

Category-level is sufficient here because each behaviour already has its own
category: `Mortgage - principal` and `Employer loan repayment` are
`committed`, `Credit card payment` is `settlement`, `Internal transfer` is
`savings`.

- `committed` — cash genuinely leaves and is not spendable: mortgage
  principal (3 407,26/month), the 800 employer loan repayment. **Subtracted
  from the pool.**
- `settlement` — credit card payments (26 912,91). **Not subtracted**; the
  card's own purchase lines already carry the spending. Subtracting these
  too would double-count roughly 27 000.
- `savings` — transfers between the user's own accounts. **Not subtracted**;
  the explicit savings target represents saving instead.

Accounting views (`v_spending`, `v_income`) are unchanged. Only the pool
calculation reads `cash_treatment`.

### New: `reimbursements`

```sql
CREATE TABLE reimbursements (
    id                       INTEGER PRIMARY KEY,
    transaction_id           INTEGER NOT NULL REFERENCES transactions(id),
    expected_from            TEXT    NOT NULL,
    expected_amount          REAL    NOT NULL,
    settled_by_transaction_id INTEGER REFERENCES transactions(id),
    settled_at               TEXT,
    note                     TEXT
);
```

Makes "13 990 owed by employer" a real queryable figure rather than a silent
exclusion.

### New: `merchant_rules`

User-taught mappings that take precedence over built-in rules. Recategorising
`Ecom Capital AS` once writes a row here, so next month's charge lands
correctly without a code change. This replaces the `CORRECTIONS` list, which
existed only to survive destructive rebuilds.

### New: `budget_config`, versioned

```sql
CREATE TABLE budget_config (
    id               INTEGER PRIMARY KEY,
    effective_from   TEXT    NOT NULL,
    income_mode      TEXT    NOT NULL CHECK (income_mode IN ('derived','manual')),
    fixed_mode       TEXT    NOT NULL CHECK (fixed_mode  IN ('derived','manual')),
    manual_income    REAL,
    manual_fixed     REAL,
    savings_target   REAL    NOT NULL,
    week_starts_on   INTEGER NOT NULL DEFAULT 1
);
```

Income and fixed costs get independent modes, because they hit the complete-
month threshold at different times: a single salary payment establishes income
sooner than a full cycle of bills establishes fixed costs. One shared flag
would force both to wait for the slower of the two.

`expected_committed` is always derived — summed from transfer categories whose
`cash_treatment` is `committed` — and has no manual override, since debt
instalments are fixed by contract rather than estimated.

Versioning by `effective_from` matters: when salary changes, past weeks must
not silently recompute.

## Budget engine

```
pool_month     = expected_income − expected_fixed − expected_committed − savings_target
daily_rate(d)  = pool_month(month of d) / days_in_month(d)
week_envelope  = Σ daily_rate(d) over the 7 days of the week
```

Summing per-day rather than picking one month matters for weeks straddling a
month boundary, where the last week of July and the first of August otherwise
disagree about what a day is worth.

Display figures:

```
today_allowance = (week_envelope − spent_before_today) / days_left_incl_today
today_remaining = today_allowance − spent_today
week_remaining  = week_envelope − spent_this_week
```

**The obvious formulation is wrong.** `remaining_week / days_left` reports
that you can still spend 683 today after already spending 700 today.
Excluding today's spending from the numerator while dividing by days
*including* today fixes it: today's allowance is fixed when the day starts,
overspend surfaces as a near-zero or negative remainder, and tomorrow
recalculates from what is genuinely left. No day ever misreports money
already gone.

`spent` counts rows whose effective treatment is `variable`, netting income
against expense — so an incoming 100 memoed `Mat` genuinely restores 100 to
groceries, and the 320 VY refund restores 320. Fixed, exceptional,
reimbursable, ignored, and all transfers are invisible here.

### Expected vs actual

Expected values are trailing averages over **complete calendar months only**.
Actual spending is measured against a pool held fixed for the month, so the
timing of individual bills is irrelevant. Without this, a mortgage landing on
the 20th would leave the app believing there was 13 288 more to spend on the
5th, and the budget would collapse mid-month.

### Cold start

There is currently no complete calendar month of data — the bank statement
starts 30 June and the card statements are partial. v1 therefore falls back
to manual `expected_income` / `expected_fixed`, seeded from the figures
derived during design, and switches to derived automatically once a full
month exists. Without this the app is broken on first run.

### Worked example

```
41 113,67  expected income (salary)
−13 463,60  fixed expenses
− 4 207,26  committed transfers (mortgage principal 3 407,26 + employer loan 800)
− 5 000,00  savings target
─────────
 18 442,81  pool for a 31-day month
    594,93  per day
  4 164,51  per week
```

Validated against real weeks: two marginal overspends (4 401,58 and
4 358,67 against the envelope) with the remaining weeks comfortably under —
a useful signal rather than noise. June weeks read low because the bank
statement begins 30 June, so those weeks are card-only.

## Ingest

Four sources normalise to one row shape before categorisation, so the future
bank fetch is a fourth source rather than a second pipeline.

1. **Manual entry** — amount first; description typing pre-selects a
   category via `categorise.py`; date defaults to today.
2. **Statement upload** — xlsx in, preview showing *new* / *already have* /
   *needs review*, then commit. Preview before write is required; a silent
   half-duplicating import is painful to unpick.
3. **Bulk API + CLI** — `POST /transactions/bulk` taking normalised rows, for
   programmatic entry.
4. **Bank fetch** — later; emits the same normalised rows.

### Ingest must become additive and idempotent

The current importer **deletes the database and rebuilds from the
spreadsheets on every run**. Correct for a script whose source of truth is
the xlsx files; fatal for an app, where manual entries exist nowhere else and
the first import after adding them would destroy them.

Identity becomes a content fingerprint: `hash(account, date, description,
amount)` plus an occurrence index. The occurrence index preserves genuine
same-day repeat purchases at one merchant while still recognising a real
re-upload, so re-importing an overlapping statement period is a no-op.

## Client

React PWA. Bottom tab bar (Home · History · Settings) plus a floating add
button — bottom tabs are what make it feel native rather than like a website.

- **Home** — today's remaining as the dominant figure, with allowance and a
  progress bar; week row beneath, tappable to reveal per-day bars. Attention
  items (uncategorised rows, unsettled reimbursements) appear as a
  dismissible banner above the number, not as a tab that never gets visited.
- **Add** — amount pad first; live category suggestion; three taps for the
  common case.
- **History** — grouped by day, running weekly total in the header. Tap to
  recategorise, which writes a `merchant_rules` entry.
- **Review** — the flagged queue (29 rows at time of writing), one row at a
  time with the rule's guess pre-filled.
- **Settings** — savings target, income mode, per-category budget treatment,
  and xlsx upload with preview.
- **Owed** — outstanding reimbursables.

**Offline:** last-loaded data is cached so Home shows a number with no
connection, which matters in shops with poor signal. **Writes require a
connection.** A full offline write queue means conflict resolution and a sync
state machine — too much machinery for one user who is nearly always
reachable over Tailscale. Additive later if it bites.

## Auth and networking

Single passcode, argon2-hashed, stored in a config file on the volume and set
on first run. Session cookie: `httpOnly`, `SameSite=Lax`, `Secure` when served
over HTTPS, 30-day expiry. In-memory rate limit on the passcode endpoint. No
user table, no roles, no registration.

Threat model, stated plainly: this stops a guest's laptop or an IoT device on
the same wifi from browsing the user's finances. It is not hardening against
a determined attacker already inside the network. The network boundary does
the real work.

The container listens on `0.0.0.0:8000`. No code distinguishes LAN from
tailnet traffic, so moving to Tailscale is purely a deployment change.

### HTTPS is required for the PWA, not optional

**Service workers only register in a secure context** — HTTPS or `localhost`.
Served as `http://192.168.1.x:8000` the app gets no service worker: no
offline caching, and no install prompt on Android. That leaves a browser tab
rather than the home-screen app the design calls for.

`tailscale serve` issues valid certificates for the tailnet hostname at no
cost and with no port forwarding, so Tailscale is not merely remote access —
it is what makes the PWA a PWA. Set up from the start.

Both paths stay functional: plain HTTP for local development on the laptop
(`localhost` is a secure context, so the service worker registers), HTTPS on
the tailnet for real use. Self-signed certificates are rejected — browser
warnings on every device, and installability still blocked in some browsers.

## Testing

**Golden-file regression on categorisation.** The 181 real transactions
become a fixture; because `categorise.py` is pure, the suite needs no
database and no I/O. This is the highest-value test in the project: it locks
in the two-coffee dedup, the `KinoTpp`/`LadingTpp` boundary bug, the memo
rules, and the loan split summing back to 13 288,75 — all real, observed
mistakes.

**Budget engine units**, targeting known-treacherous areas:

- `today_allowance` not misreporting money already spent
- a week straddling a month boundary with differing daily rates
- overspend producing a negative remainder rather than clamping to zero
- each `cash_treatment`: `committed` subtracts, `settlement` and `savings` do not
- cold start with no complete calendar month

**Ingest idempotency**, as named tests because these are observed failures:
same file twice yields no duplicates; overlapping periods yield no
duplicates; two identical same-day purchases are both retained.

**Reconciliation invariant.** One assertion that the dataset's net total is
14 084,24 — cheap, and catches accidental row loss anywhere in the pipeline.

**API contract tests** via FastAPI `TestClient`: auth required on every
route, passcode flow, bulk insert validation.

**No browser E2E in v1.** Fragile machinery for little signal at one user; a
manual smoke test on the real device is more informative.

## Migration from current state

1. `git init` — done; the previous `.git` had no objects and no `HEAD`.
2. Move `db/transactions.db` to `data/` for the volume mount. No re-import
   needed.
3. Add schema migrations for the new columns and tables above.
4. Split `import_transactions.py` into the modules listed under Repo layout.
5. Convert ingest from destructive-rebuild to additive-with-fingerprint.
6. Backfill `fingerprint` and `occurrence` for the existing 181 rows.
7. Migrate the `CORRECTIONS` entries into `merchant_rules` and per-row
   `budget_override` values, then delete the list.
8. Set the 13 990 phone to `budget_override = 'reimbursable'` and create its
   `reimbursements` row against the employer.

## Deferred: bank integration

Researched during design, deliberately out of v1.

- **Direct DNB PSD2 access is not viable.** Acting as one's own AISP requires
  a PSD2 licence and a qualified eSeal certificate (roughly €1–2k/yr).
- **The former free path is closed.** GoCardless Bank Account Data (formerly
  Nordigen), which had a free personal tier covering DNB, is shut to new
  signups as of 2026.
- **One viable route remains:** Enable Banking's "Restricted Production"
  tier — free, real production data, limited to accounts the developer links
  themselves, DNB covered.
- **PSD2 consent expires** (historically ~90 days) and requires
  re-authentication with SCA. "Automatic" still means periodic manual
  re-approval in the DNB app. No self-hosted design avoids this.

Needs its own spike (can the signup be completed, is DNB genuinely
reachable, what does the consent flow look like) followed by its own spec.
The ingest pipeline is designed so it lands as a fourth source.

## Open questions

Not blocking implementation; each has a stated default.

1. **The +835,80 Giro from Nordvest Teknikk AS** (2026-07-24) is still categorised as
   employer reimbursement on a guess, and counted as income. Given the 800
   outgoing turned out to be a loan repayment, it may be the other leg of the
   same arrangement. Default: leave flagged as income until confirmed.
2. **`MAULUND A/S` (298) and `Ecom Capital AS` (210)** remain unidentified.
   Default: stay in `Uncategorised`, flagged.
3. **Clothing & shoes** is `variable` but may belong in `exceptional`.
   Default: `variable`, changeable in Settings.
4. **Savings target value** is not yet set; 5 000 is used illustratively.
   Default: prompt on first run.
