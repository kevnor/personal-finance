# Domain Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tested, HTTP-free domain core of the personal finance app — schema migrations, statement ingest, categorisation, derived rows, and the weekly-envelope budget engine — shipping as an importable package plus a CLI.

**Architecture:** Pure-Python package under `server/lib/`, stdlib only. Each module has one responsibility and a narrow interface: `store` owns persistence and migrations, `ingest/` turns statement files into normalised rows, `categorise` is a pure description-to-category function, `derive` expands itemised rows, `budget` computes the envelope. No module imports FastAPI; nothing here knows HTTP exists. This is what Plan 2 (API/auth/Docker) and Plan 3 (PWA) will sit on top of.

**Tech Stack:** Python 3.14, stdlib `sqlite3` / `zipfile` / `xml.etree` / `hashlib` / `dataclasses`, pytest 9.0.2. No third-party runtime dependencies.

**Spec:** [docs/superpowers/specs/2026-08-22-personal-finance-app-design.md](../specs/2026-08-22-personal-finance-app-design.md)

## Global Constraints

- **Python 3.14** — already installed as `python3`. Verify with `python3 --version`.
- **Stdlib only at runtime.** No `openpyxl`, no `pandas`, no `pydantic` in this plan. The xlsx reader is hand-rolled on `zipfile` + `xml.etree` because neither library is installed and the parsing need is narrow. pytest is a dev dependency and is already present (9.0.2).
- **Run tests with `python3 -m pytest`** from the repo root. There is no `pytest` binary on PATH and no virtualenv; do not create one.
- **Sign convention:** `amount > 0` is money in, `amount < 0` is money out. Never store an unsigned amount.
- **Dates are ISO `YYYY-MM-DD` strings** everywhere in Python and SQLite. Source spreadsheets use Excel serials with epoch 1899-12-30; convert at the ingest boundary and never let a serial past it.
- **Currency is NOK**, stored as `REAL`. Round to 2 decimals with `round(x, 2)` at every arithmetic boundary.
- **Reconciliation invariant:** the three statements in `input/` must yield **181 transactions** with a net total of **14 084,24**. Any change that breaks this is a regression.
- **Norwegian text is data.** Descriptions contain `æøå` and `Æ`. Open every file with `encoding="utf-8"` explicitly; never rely on locale default.
- **No destructive rebuilds.** Ingest is additive and idempotent. Never `DROP`/recreate a table or delete the database outside a migration.
- **The existing `db/import_transactions.py` is the reference implementation** at commit `d0f2b9a`. Rules and constants are moved from it verbatim unless a step says otherwise. Delete it only in Task 10.
- **Data files are gitignored** (`db/*.csv`, `db/import.sql`, `data/`, `input/`). Never `git add -f` them.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, pytest config |
| `db/migrations/001_baseline.sql` | Current schema as the migration baseline |
| `db/migrations/002_budget.sql` | Budget treatment, reimbursements, merchant rules, config |
| `server/lib/store.py` | Connection, migration runner, transaction upsert |
| `server/lib/categorise.py` | Pure: description → category. No I/O. |
| `server/lib/derive.py` | Pure: itemised row → derived rows (loan splitter) |
| `server/lib/ingest/dnb_xlsx.py` | xlsx → `RawRow` list. Knows layouts, not categories. |
| `server/lib/ingest/fingerprint.py` | Content fingerprint + occurrence index |
| `server/lib/budget.py` | Pool, envelope, today's figures |
| `server/cli.py` | `import` and `reconcile` commands |
| `server/test/` | One test module per lib module |
| `server/test/fixtures/categorisation.json` | Golden file: 181 description→category pairs |

---

## Task 1: Project scaffolding and migration runner

**Files:**
- Create: `pyproject.toml`
- Create: `server/__init__.py`, `server/lib/__init__.py`, `server/lib/ingest/__init__.py`, `server/test/__init__.py`
- Create: `server/lib/store.py`
- Create: `db/migrations/001_baseline.sql`
- Test: `server/test/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `store.connect(path: str | Path) -> sqlite3.Connection` — row factory set to `sqlite3.Row`, foreign keys on.
  - `store.migrate(con: sqlite3.Connection, migrations_dir: str | Path) -> list[str]` — applies unapplied `*.sql` files in filename order, records them in `schema_migrations`, returns the names applied this call.

- [ ] **Step 1: Write the failing test**

Create `server/test/test_store.py`:

```python
import sqlite3
from pathlib import Path

from server.lib import store

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


def test_migrate_applies_baseline_then_is_idempotent(tmp_path):
    db = tmp_path / "t.db"
    con = store.connect(db)

    first = store.migrate(con, MIGRATIONS)
    assert "001_baseline.sql" in first

    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"accounts", "categories", "transactions", "import_batches"} <= tables

    second = store.migrate(con, MIGRATIONS)
    assert second == []


def test_connect_enables_foreign_keys(tmp_path):
    con = store.connect(tmp_path / "t.db")
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connect_returns_row_objects(tmp_path):
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)
    con.execute("INSERT INTO accounts (name, kind) VALUES ('A', 'bank')")
    row = con.execute("SELECT name, kind FROM accounts").fetchone()
    assert row["name"] == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Create the package files and pyproject**

Create `pyproject.toml`:

```toml
[project]
name = "personal-finance"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = []

[tool.pytest.ini_options]
testpaths = ["server/test"]
pythonpath = ["."]
```

Create four empty files: `server/__init__.py`, `server/lib/__init__.py`, `server/lib/ingest/__init__.py`, `server/test/__init__.py`.

- [ ] **Step 4: Create the baseline migration**

Copy the current schema into the migration, adding the migrations table.

Create `db/migrations/001_baseline.sql`:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    name       TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('bank', 'credit_card'))
);

CREATE TABLE IF NOT EXISTS categories (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,
    kind   TEXT NOT NULL CHECK (kind IN ('expense', 'income', 'transfer')),
    parent TEXT
);

CREATE TABLE IF NOT EXISTS import_batches (
    id           INTEGER PRIMARY KEY,
    source_file  TEXT NOT NULL,
    row_count    INTEGER NOT NULL,
    skipped_rows INTEGER NOT NULL DEFAULT 0,
    imported_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY,
    date         TEXT    NOT NULL,
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    description  TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    category_id  INTEGER REFERENCES categories(id),
    is_transfer  INTEGER NOT NULL DEFAULT 0 CHECK (is_transfer IN (0, 1)),
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    counterparty TEXT,
    memo         TEXT,
    note         TEXT,
    batch_id     INTEGER NOT NULL REFERENCES import_batches(id),
    source_row   INTEGER NOT NULL,
    is_derived   INTEGER NOT NULL DEFAULT 0 CHECK (is_derived IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_tx_review   ON transactions(needs_review);
```

Note: the old `UNIQUE (batch_id, source_row, description, amount)` constraint is deliberately absent. Task 6 replaces it with a fingerprint-based unique index, which is what makes re-import idempotent rather than merely duplicate-tolerant.

- [ ] **Step 5: Write the store implementation**

Create `server/lib/store.py`:

```python
"""Persistence: connections, migrations, and transaction writes."""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def migrate(con: sqlite3.Connection, migrations_dir: str | Path) -> list[str]:
    """Apply every unapplied migration in filename order. Returns names applied."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r["name"] for r in con.execute("SELECT name FROM schema_migrations")}

    applied: list[str] = []
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        if path.name in done:
            continue
        con.executescript(path.read_text(encoding="utf-8"))
        con.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (path.name, now))
        applied.append(path.name)
    con.commit()
    return applied
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_store.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml server/__init__.py server/lib/__init__.py \
        server/lib/ingest/__init__.py server/test/__init__.py \
        server/lib/store.py db/migrations/001_baseline.sql \
        server/test/test_store.py
git commit -m "feat: add package scaffolding and migration runner"
```

---

## Task 2: Budget schema migration

**Files:**
- Create: `db/migrations/002_budget.sql`
- Test: `server/test/test_migrations.py`

**Interfaces:**
- Consumes: `store.connect`, `store.migrate` from Task 1.
- Produces: schema columns and tables that Tasks 6–9 write to — `categories.budget_treatment`, `categories.cash_treatment`, `transactions.budget_override`, `transactions.origin`, `transactions.fingerprint`, `transactions.occurrence`, and tables `reimbursements`, `merchant_rules`, `budget_config`.

- [ ] **Step 1: Write the failing test**

Create `server/test/test_migrations.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from server.lib import store

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.migrate(c, MIGRATIONS)
    return c


def cols(con, table):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def test_category_treatment_columns_exist(con):
    assert {"budget_treatment", "cash_treatment"} <= cols(con, "categories")


def test_transaction_budget_columns_exist(con):
    assert {"budget_override", "origin", "fingerprint", "occurrence"} <= cols(
        con, "transactions")


def test_new_tables_exist(con):
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"reimbursements", "merchant_rules", "budget_config"} <= tables


def test_budget_treatment_rejects_unknown_value(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO categories (name, kind, budget_treatment)"
            " VALUES ('X', 'expense', 'nonsense')")


def test_cash_treatment_rejects_unknown_value(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO categories (name, kind, cash_treatment)"
            " VALUES ('Y', 'transfer', 'nonsense')")


def test_budget_override_rejects_unknown_value(con):
    con.execute("INSERT INTO accounts (name, kind) VALUES ('A', 'bank')")
    con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('f', 1, '2026-01-01')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO transactions"
            " (date, account_id, description, amount, batch_id, source_row,"
            "  fingerprint, budget_override)"
            " VALUES ('2026-01-01', 1, 'd', -1.0, 1, 2, 'abc', 'nonsense')")


def test_budget_config_defaults_week_to_monday(con):
    con.execute(
        "INSERT INTO budget_config"
        " (effective_from, income_mode, fixed_mode, savings_target)"
        " VALUES ('2026-01-01', 'manual', 'manual', 5000.0)")
    assert con.execute(
        "SELECT week_starts_on FROM budget_config").fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_migrations.py -v`
Expected: FAIL — `no such column: budget_treatment`

- [ ] **Step 3: Write the migration**

Create `db/migrations/002_budget.sql`:

```sql
ALTER TABLE categories ADD COLUMN budget_treatment TEXT NOT NULL DEFAULT 'variable'
    CHECK (budget_treatment IN ('fixed','variable','exceptional'));

-- Read ONLY for categories whose kind = 'transfer'; ignored otherwise.
ALTER TABLE categories ADD COLUMN cash_treatment TEXT NOT NULL DEFAULT 'settlement'
    CHECK (cash_treatment IN ('committed','settlement','savings'));

ALTER TABLE transactions ADD COLUMN budget_override TEXT
    CHECK (budget_override IN ('fixed','variable','exceptional','reimbursable','ignore'));

ALTER TABLE transactions ADD COLUMN origin TEXT NOT NULL DEFAULT 'import'
    CHECK (origin IN ('manual','import','bank','derived'));

ALTER TABLE transactions ADD COLUMN fingerprint TEXT NOT NULL DEFAULT '';

ALTER TABLE transactions ADD COLUMN occurrence INTEGER NOT NULL DEFAULT 1;

CREATE TABLE reimbursements (
    id                        INTEGER PRIMARY KEY,
    transaction_id            INTEGER NOT NULL REFERENCES transactions(id),
    expected_from             TEXT    NOT NULL,
    expected_amount           REAL    NOT NULL,
    settled_by_transaction_id INTEGER REFERENCES transactions(id),
    settled_at                TEXT,
    note                      TEXT
);

CREATE TABLE merchant_rules (
    id          INTEGER PRIMARY KEY,
    pattern     TEXT    NOT NULL UNIQUE,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    created_at  TEXT    NOT NULL
);

CREATE TABLE budget_config (
    id             INTEGER PRIMARY KEY,
    effective_from TEXT    NOT NULL,
    income_mode    TEXT    NOT NULL CHECK (income_mode IN ('derived','manual')),
    fixed_mode     TEXT    NOT NULL CHECK (fixed_mode  IN ('derived','manual')),
    manual_income  REAL,
    manual_fixed   REAL,
    savings_target REAL    NOT NULL,
    week_starts_on INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_tx_fingerprint ON transactions(fingerprint);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_migrations.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -v`
Expected: PASS, 10 tests. Task 1's idempotency test must still pass with two migrations present.

- [ ] **Step 6: Commit**

```bash
git add db/migrations/002_budget.sql server/test/test_migrations.py
git commit -m "feat: add budget treatment, reimbursement and config schema"
```

---

## Task 3: Pure categorisation with golden-file regression

**Files:**
- Create: `server/lib/categorise.py`
- Create: `server/test/fixtures/categorisation.json`
- Test: `server/test/test_categorise.py`

**Interfaces:**
- Consumes: nothing (this module is pure and standalone).
- Produces:
  - `categorise.Verdict` — frozen dataclass with fields `category: str`, `needs_review: bool`.
  - `categorise.categorise(description: str, learned: Mapping[str, str] | None = None) -> Verdict` — `learned` maps a lowercase substring to a category name and takes precedence over built-in rules.
  - `categorise.CATEGORIES: list[tuple[str, str]]` — `(name, kind)` pairs, used by Task 10 to seed the table.
  - `categorise.extract_counterparty(description: str) -> str | None`

- [ ] **Step 1: Generate the golden fixture from the current database**

The existing database is the verified source of truth for expected categories. Generate the fixture rather than hand-writing 181 entries.

Run:

```bash
python3 - <<'EOF'
import json, sqlite3
con = sqlite3.connect("db/transactions.db")
rows = [
    {"description": d, "amount": a, "category": c, "needs_review": bool(n)}
    for d, a, c, n in con.execute(
        "SELECT t.description, t.amount, c.name, t.needs_review "
        "FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.is_derived = 0 ORDER BY t.date, t.id")
]
with open("server/test/fixtures/categorisation.json", "w", encoding="utf-8") as fh:
    json.dump(rows, fh, ensure_ascii=False, indent=1)
print(len(rows), "rows written")
EOF
```

Expected: `178 rows written` — 181 total minus the 3 derived mortgage rows, which Task 4 covers separately.

Note: rows whose category came from the `CORRECTIONS` override — the 166 Ingvild `Bok` gift and Torkel' 55 share, both `Gifts` — are *not* reproducible by rules alone. Step 4's test excludes them explicitly by description; Task 9 covers them.

- [ ] **Step 2: Write the failing test**

Create `server/test/test_categorise.py`:

```python
import json
from pathlib import Path

import pytest

from server.lib import categorise

FIXTURE = Path(__file__).parent / "fixtures" / "categorisation.json"

# Assigned by the account holder, not derivable from text. Covered in Task 9.
CORRECTED = ("Ingvild Kvamme Berg BokTpp", "Torkel Aalborg BokTpp")


def golden():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [r for r in rows if not any(c in r["description"] for c in CORRECTED)]


@pytest.mark.parametrize("row", golden(), ids=lambda r: r["description"][:40])
def test_golden_categorisation(row):
    assert categorise.categorise(row["description"]).category == row["category"]


def test_memo_glued_to_tpp_suffix_still_matches():
    """Regression: \\b fails between 'Kino' and 'Tpp' — both are word chars."""
    assert categorise.categorise(
        "Overføring  9230000000 Vetle Nyhus Dahl KinoTpp: Vipps"
    ).category == "Entertainment"
    assert categorise.categorise(
        "Overføring  92200000000 Ingvild Kvamme Berg LadingTpp: Vipps"
    ).category == "Fuel & EV charging"


def test_unmatched_vipps_is_flagged_for_review():
    v = categorise.categorise("Overføring  90200000000 Ingvild Kvamme Berg Tpp: Vipps")
    assert v.category == "Vipps P2P - unspecified"
    assert v.needs_review is True


def test_unknown_merchant_is_uncategorised_and_flagged():
    v = categorise.categorise("Visa  100121  Ecom Capital AS")
    assert v.category == "Uncategorised"
    assert v.needs_review is True


def test_learned_rule_beats_builtin_rule():
    v = categorise.categorise(
        "Varekjøp Rema Lorenveien Lørenveien 3 Oslo",
        learned={"rema lorenveien": "Restaurants & takeaway"})
    assert v.category == "Restaurants & takeaway"
    assert v.needs_review is False


def test_is_pure_no_arguments_mutated():
    learned = {"foo": "Groceries"}
    categorise.categorise("foo bar", learned=learned)
    assert learned == {"foo": "Groceries"}


def test_counterparty_extracted_from_vipps_star_form():
    assert categorise.extract_counterparty(
        "Vipps*Ingvild Kvamme B, Oslo") == "Ingvild Kvamme B"


def test_counterparty_none_for_plain_merchant():
    assert categorise.extract_counterparty("JOKER LØREN STA, Oslo") is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_categorise.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.lib.categorise'`

- [ ] **Step 4: Write the module**

Create `server/lib/categorise.py`. Move `CATEGORIES`, `RULES`, `VIPPS_RE` and `extract_counterparty` **verbatim** from `db/import_transactions.py` at commit `d0f2b9a` (lines 58–156 and 223–244), then wrap the lookup in the pure signature below. Do not retune any regex — the golden fixture encodes their current, verified behaviour.

Three changes to the moved code, and only these:

1. `RULES` entries stay `(pattern, category, needs_review)` triples.
2. `categorise` drops its unused `amount` parameter and gains `learned`.
3. It returns a `Verdict` instead of a tuple.

```python
"""Pure categorisation: description text in, category out. No I/O."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

# --- CATEGORIES, RULES, VIPPS_RE moved verbatim from
# --- db/import_transactions.py @ d0f2b9a (lines 58-156). Do not retune.
CATEGORIES = [...]   # (name, kind) pairs
RULES = [...]        # (pattern, category, needs_review) triples
VIPPS_RE = re.compile(r"vipps|tpp:|overf.ring", re.I)


@dataclass(frozen=True)
class Verdict:
    category: str
    needs_review: bool


def categorise(description: str,
               learned: Mapping[str, str] | None = None) -> Verdict:
    """Map a statement description to a category.

    `learned` maps a lowercase substring to a category name and wins over the
    built-in rules, so a correction taught once keeps applying.
    """
    low = description.lower()

    for fragment, category in (learned or {}).items():
        if fragment.lower() in low:
            return Verdict(category, False)

    for pattern, category, review in RULES:
        if re.search(pattern, low):
            return Verdict(category, bool(review))

    if VIPPS_RE.search(low):
        return Verdict("Vipps P2P - unspecified", True)
    return Verdict("Uncategorised", True)


def extract_counterparty(description: str) -> str | None:
    ...  # moved verbatim from db/import_transactions.py @ d0f2b9a
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_categorise.py -v`
Expected: PASS. 176 parametrised golden cases plus 8 named tests.

If any golden case fails, the moved rules differ from the reference. Diff against `git show d0f2b9a:db/import_transactions.py` rather than adjusting the fixture — the fixture is the verified truth.

- [ ] **Step 6: Commit**

```bash
git add server/lib/categorise.py server/test/test_categorise.py \
        server/test/fixtures/categorisation.json
git commit -m "feat: extract pure categorisation with golden-file regression"
```

---

## Task 4: Loan splitter

**Files:**
- Create: `server/lib/derive.py`
- Test: `server/test/test_derive.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `derive.DerivedRow` — frozen dataclass with `description: str`, `amount: float`, `category: str`.
  - `derive.split_loan_term(description: str, amount: float) -> list[DerivedRow]` — returns `[]` when the description carries no `Avdrag`/`Renter` itemisation.

- [ ] **Step 1: Write the failing test**

Create `server/test/test_derive.py`:

```python
from server.lib import derive

LOAN = ("Lån  422687 Lån 1516.09.18257 "
        "Avdrag Kr 3.407,26Renter Kr 9.816,49")


def test_splits_into_interest_principal_and_fee():
    rows = derive.split_loan_term(LOAN, -13288.75)
    assert {r.category for r in rows} == {
        "Mortgage - interest", "Mortgage - principal", "Mortgage - fees"}


def test_parts_sum_back_to_the_original_charge():
    rows = derive.split_loan_term(LOAN, -13288.75)
    assert round(sum(r.amount for r in rows), 2) == -13288.75


def test_interest_and_principal_parsed_from_norwegian_number_format():
    by_cat = {r.category: r.amount
              for r in derive.split_loan_term(LOAN, -13288.75)}
    assert by_cat["Mortgage - interest"] == -9816.49
    assert by_cat["Mortgage - principal"] == -3407.26
    assert by_cat["Mortgage - fees"] == -65.0


def test_no_fee_row_when_parts_account_for_the_whole_charge():
    rows = derive.split_loan_term(LOAN, -13223.75)
    assert {r.category for r in rows} == {
        "Mortgage - interest", "Mortgage - principal"}


def test_returns_empty_for_a_non_loan_description():
    assert derive.split_loan_term("Varekjøp Rema Lorenveien", -161.14) == []


def test_returns_empty_when_only_one_component_present():
    assert derive.split_loan_term("Lån 123 Avdrag Kr 100,00", -100.0) == []


def test_derived_amounts_keep_the_sign_of_the_source():
    rows = derive.split_loan_term(LOAN, -13288.75)
    assert all(r.amount < 0 for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_derive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.lib.derive'`

- [ ] **Step 3: Write the module**

Create `server/lib/derive.py`:

```python
"""Expand itemised statement rows into their component parts.

A loan term line states principal and interest inside its own description.
Interest and any fee are real expenses; principal is debt repayment, booked
as a transfer so it stays out of spending reports while still reducing the
budget pool (see budget.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

AVDRAG_RE = re.compile(r"avdrag\s+kr\s*([\d.]+,\d{2})", re.I)
RENTER_RE = re.compile(r"renter\s+kr\s*([\d.]+,\d{2})", re.I)


@dataclass(frozen=True)
class DerivedRow:
    description: str
    amount: float
    category: str


def _nok(text: str) -> float:
    """Parse Norwegian number format: '3.407,26' -> 3407.26."""
    return float(text.replace(".", "").replace(",", "."))


def split_loan_term(description: str, amount: float) -> list[DerivedRow]:
    avdrag = AVDRAG_RE.search(description)
    renter = RENTER_RE.search(description)
    if not (avdrag and renter):
        return []

    principal = _nok(avdrag.group(1))
    interest = _nok(renter.group(1))
    fee = round(abs(amount) - principal - interest, 2)

    parts = [("Mortgage - interest", interest),
             ("Mortgage - principal", principal)]
    if abs(fee) >= 0.01:
        parts.append(("Mortgage - fees", fee))

    sign = -1.0 if amount < 0 else 1.0
    return [
        DerivedRow(f"{description}  [{category.split(' - ')[1]}]",
                   round(sign * value, 2), category)
        for category, value in parts
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_derive.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add server/lib/derive.py server/test/test_derive.py
git commit -m "feat: add loan term splitter"
```

---

## Task 5: DNB statement parsing

**Files:**
- Create: `server/lib/ingest/dnb_xlsx.py`
- Test: `server/test/test_dnb_xlsx.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `dnb_xlsx.RawRow` — frozen dataclass: `date: str` (ISO), `description: str`, `amount: float` (signed), `source_row: int` (1-based sheet row).
  - `dnb_xlsx.BANK` and `dnb_xlsx.CARD` — `Layout` instances describing column positions.
  - `dnb_xlsx.read_statement(path: str | Path, layout: Layout) -> list[RawRow]` — skips the header, blank rows, and invoice carry-over rows.

- [ ] **Step 1: Write the failing test**

Create `server/test/test_dnb_xlsx.py`:

```python
from pathlib import Path

import pytest

from server.lib.ingest import dnb_xlsx

INPUT = Path(__file__).resolve().parents[2] / "input"

BANK_FILE = INPUT / "Kontoutskrift.xlsx"
CARD_1 = INPUT / "transaksjonsliste(1).xlsx"
CARD_2 = INPUT / "transaksjonsliste.xlsx"

pytestmark = pytest.mark.skipif(
    not BANK_FILE.exists(), reason="statements not present")


def test_bank_statement_row_count():
    assert len(dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)) == 123


def test_card_statements_exclude_invoice_carryover_rows():
    # Each card file opens with 'Skyldig beløp fra forrige faktura', which is
    # a balance, not a transaction. 44 and 14 data rows respectively.
    assert len(dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)) == 43
    assert len(dnb_xlsx.read_statement(CARD_2, dnb_xlsx.CARD)) == 13
    for path in (CARD_1, CARD_2):
        for row in dnb_xlsx.read_statement(path, dnb_xlsx.CARD):
            assert "forrige faktura" not in row.description.lower()


def test_excel_serial_converted_to_iso_date():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    assert rows[0].date == "2026-06-30"
    assert all(len(r.date) == 10 and r.date[4] == "-" for r in rows)


def test_outgoing_is_negative_and_incoming_positive():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    by_desc = {r.description: r.amount for r in rows}
    assert by_desc["Lønn  900112233 Nordvest Teknikk AS"] == 41113.67
    grocery = next(v for k, v in by_desc.items() if "Rema Lorenveien" in k)
    assert grocery < 0


def test_norwegian_characters_survive_parsing():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    assert any("Løren" in r.description for r in rows)
    assert any("ø" in r.description or "æ" in r.description for r in rows)


def test_source_row_is_one_based_and_unique():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    numbers = [r.source_row for r in rows]
    assert len(set(numbers)) == len(numbers)
    assert min(numbers) >= 2  # row 1 is the header


def test_bank_and_card_totals_match_the_known_net():
    total = sum(r.amount for r in
                dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK))
    total += sum(r.amount for r in
                 dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD))
    total += sum(r.amount for r in
                 dnb_xlsx.read_statement(CARD_2, dnb_xlsx.CARD))
    assert round(total, 2) == 14084.24
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_dnb_xlsx.py -v`
Expected: FAIL — `ImportError: cannot import name 'dnb_xlsx'`

- [ ] **Step 3: Write the module**

Create `server/lib/ingest/dnb_xlsx.py`. The sheet reader is moved from `db/import_transactions.py` @ `d0f2b9a` (lines 19–56); the layout abstraction and carry-over filter are new.

```python
"""Read DNB xlsx statement exports into normalised rows.

Hand-rolled on zipfile + ElementTree: openpyxl is not installed, and the
parsing need is narrow (one sheet, no formulas, no styling).

Knows about spreadsheet layouts. Knows nothing about categories.
"""
from __future__ import annotations

import datetime
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXCEL_EPOCH = datetime.date(1899, 12, 30)
CARRYOVER_RE = re.compile(r"skyldig bel.p fra forrige faktura", re.I)


@dataclass(frozen=True)
class Layout:
    """Zero-based column positions for one statement format."""
    date: int
    description: int
    incoming: int
    outgoing: int


# Kontoutskrift: Dato | Forklaring | Rentedato | Ut fra konto | Inn på konto
BANK = Layout(date=0, description=1, incoming=4, outgoing=3)
# Transaksjonsliste: Dato | Beløpet gjelder | Valuta | Kurs | Inn | Ut
CARD = Layout(date=0, description=1, incoming=4, outgoing=5)


@dataclass(frozen=True)
class RawRow:
    date: str
    description: str
    amount: float
    source_row: int


def _column_index(ref: str) -> int:
    n = 0
    for char in re.match(r"([A-Z]+)", ref).group(1):
        n = n * 26 + ord(char) - 64
    return n - 1


def _sheet_rows(path: str | Path) -> list[list[str]]:
    archive = zipfile.ZipFile(path)

    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    rows: list[list[str]] = []
    sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter(f"{NS}row"):
        cells: dict[int, str] = {}
        for cell in row.findall(f"{NS}c"):
            kind = cell.get("t")
            value = cell.find(f"{NS}v")
            inline = cell.find(f"{NS}is")
            if kind == "inlineStr" and inline is not None:
                text = "".join(t.text or "" for t in inline.iter(f"{NS}t"))
            elif kind == "s" and value is not None:
                text = shared[int(value.text)]
            elif value is not None:
                text = value.text
            else:
                continue
            cells[_column_index(cell.get("r"))] = text
        rows.append([cells.get(i) or "" for i in range(max(cells) + 1)]
                    if cells else [])
    return rows


def _to_iso(serial: str) -> str:
    return (EXCEL_EPOCH + datetime.timedelta(days=int(float(serial)))).isoformat()


def _to_float(text: str) -> float:
    text = (text or "").strip()
    return float(text) if text else 0.0


def read_statement(path: str | Path, layout: Layout) -> list[RawRow]:
    width = max(layout.date, layout.description,
                layout.incoming, layout.outgoing) + 1

    out: list[RawRow] = []
    for lineno, raw in enumerate(_sheet_rows(path), start=1):
        if lineno == 1:
            continue                                    # header
        row = raw + [""] * (width - len(raw))
        description = (row[layout.description] or "").strip()
        if not description or not (row[layout.date] or "").strip():
            continue
        if CARRYOVER_RE.search(description):            # balance, not a transaction
            continue
        amount = round(_to_float(row[layout.incoming])
                       - _to_float(row[layout.outgoing]), 2)
        out.append(RawRow(_to_iso(row[layout.date]), description,
                          amount, lineno))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_dnb_xlsx.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add server/lib/ingest/dnb_xlsx.py server/test/test_dnb_xlsx.py
git commit -m "feat: add DNB xlsx statement reader"
```

---

## Task 6: Fingerprint identity and idempotent upsert

**Files:**
- Create: `server/lib/ingest/fingerprint.py`
- Modify: `server/lib/store.py` — append `upsert_transactions`
- Create: `db/migrations/003_fingerprint_unique.sql`
- Test: `server/test/test_fingerprint.py`, `server/test/test_upsert.py`

**Interfaces:**
- Consumes: `dnb_xlsx.RawRow` (Task 5), `store.connect`/`migrate` (Task 1).
- Produces:
  - `fingerprint.fingerprint(account: str, date: str, description: str, amount: float) -> str` — 16-char hex digest.
  - `fingerprint.with_identity(rows: list[RawRow], account: str) -> list[tuple[RawRow, str, int]]` — pairs each row with its fingerprint and 1-based occurrence index among rows sharing that fingerprint.
  - `store.upsert_transactions(con, rows, account_id, account_name, batch_id, categoriser) -> tuple[int, int]` — returns `(inserted, skipped_existing)`. `categoriser` is a callable `(str) -> categorise.Verdict`.

- [ ] **Step 1: Write the failing fingerprint test**

Create `server/test/test_fingerprint.py`:

```python
from server.lib.ingest import dnb_xlsx, fingerprint


def row(date, desc, amount, source_row=2):
    return dnb_xlsx.RawRow(date, desc, amount, source_row)


def test_fingerprint_is_stable_for_identical_input():
    a = fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -100.0)
    b = fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -100.0)
    assert a == b


def test_fingerprint_differs_on_any_field():
    base = fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -100.0)
    assert base != fingerprint.fingerprint("Kredittkort", "2026-07-01", "Rema", -100.0)
    assert base != fingerprint.fingerprint("Bankkonto", "2026-07-02", "Rema", -100.0)
    assert base != fingerprint.fingerprint("Bankkonto", "2026-07-01", "Meny", -100.0)
    assert base != fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -101.0)


def test_fingerprint_ignores_source_row():
    """Row position must not affect identity, or re-ordered exports duplicate."""
    rows = [row("2026-07-01", "Rema", -100.0, 5),
            row("2026-07-01", "Rema", -100.0, 99)]
    ids = {fp for _, fp, _ in fingerprint.with_identity(rows, "Bankkonto")}
    assert len(ids) == 1


def test_repeat_purchases_get_distinct_occurrence_numbers():
    """Two coffees at one shop on one day are two real transactions."""
    rows = [row("2026-06-30", "PROUD MARY OSLO, Oslo", -238.0, 17),
            row("2026-06-30", "PROUD MARY OSLO, Oslo", -238.0, 19)]
    got = fingerprint.with_identity(rows, "Kredittkort")
    assert [occ for _, _, occ in got] == [1, 2]


def test_distinct_rows_all_get_occurrence_one():
    rows = [row("2026-07-01", "Rema", -100.0),
            row("2026-07-01", "Meny", -100.0)]
    assert [occ for _, _, occ in fingerprint.with_identity(rows, "Bankkonto")] == [1, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_fingerprint.py -v`
Expected: FAIL — `ImportError: cannot import name 'fingerprint'`

- [ ] **Step 3: Write the fingerprint module**

Create `server/lib/ingest/fingerprint.py`:

```python
"""Content-based transaction identity.

Statement exports carry no stable transaction id, so identity is derived
from content. Row position is deliberately excluded: a re-export may order
rows differently, and position-based identity would duplicate the lot.

Because the same merchant, day and amount can occur twice for real (two
coffees paid separately), identity is the fingerprint *plus* an occurrence
index. Keying on the fingerprint alone silently discards real spending.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from server.lib.ingest.dnb_xlsx import RawRow


def fingerprint(account: str, date: str, description: str,
                amount: float) -> str:
    payload = "\x1f".join(
        (account, date, description.strip(), f"{amount:.2f}"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def with_identity(rows: list[RawRow],
                  account: str) -> list[tuple[RawRow, str, int]]:
    seen: dict[str, int] = defaultdict(int)
    out: list[tuple[RawRow, str, int]] = []
    for row in rows:
        fp = fingerprint(account, row.date, row.description, row.amount)
        seen[fp] += 1
        out.append((row, fp, seen[fp]))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_fingerprint.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Write the unique-index migration**

Create `db/migrations/003_fingerprint_unique.sql`:

```sql
CREATE UNIQUE INDEX idx_tx_identity
    ON transactions(account_id, fingerprint, occurrence)
    WHERE is_derived = 0;
```

The partial index excludes derived rows, which share their parent's
fingerprint by design (Task 4 emits three rows from one source row).

- [ ] **Step 6: Write the failing upsert test**

Create `server/test/test_upsert.py`:

```python
from pathlib import Path

import pytest

from server.lib import categorise, store
from server.lib.ingest import dnb_xlsx

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "db" / "migrations"
CARD_1 = ROOT / "input" / "transaksjonsliste(1).xlsx"
CARD_2 = ROOT / "input" / "transaksjonsliste.xlsx"

pytestmark = pytest.mark.skipif(
    not CARD_1.exists(), reason="statements not present")


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.migrate(c, MIGRATIONS)
    c.execute("INSERT INTO accounts (name, kind) VALUES ('Kredittkort', 'credit_card')")
    for name, kind in categorise.CATEGORIES:
        c.execute("INSERT INTO categories (name, kind) VALUES (?, ?)", (name, kind))
    c.commit()
    return c


def load(con, path, label="f"):
    batch = con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES (?, 0, '2026-08-22')", (label,)).lastrowid
    rows = dnb_xlsx.read_statement(path, dnb_xlsx.CARD)
    return store.upsert_transactions(
        con, rows, account_id=1, account_name="Kredittkort",
        batch_id=batch, categoriser=categorise.categorise)


def count(con):
    return con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]


def test_first_import_inserts_every_row(con):
    inserted, skipped = load(con, CARD_1)
    assert (inserted, skipped) == (43, 0)
    assert count(con) == 43


def test_reimporting_the_same_file_is_a_noop(con):
    load(con, CARD_1)
    inserted, skipped = load(con, CARD_1, "again")
    assert inserted == 0
    assert skipped == 43
    assert count(con) == 43


def test_repeat_same_day_purchases_are_both_retained(con):
    """Regression: keying identity on date+description+amount alone silently
    dropped one 238 and one 119 — two coffees bought separately on
    2026-06-30. Both pairs must survive."""
    load(con, CARD_1)
    counts = dict(con.execute(
        "SELECT amount, COUNT(*) FROM transactions"
        " WHERE upper(description) LIKE 'PROUD MARY OSLO, OSLO%'"
        "   AND date = '2026-06-30' GROUP BY amount"))
    assert counts[-238.0] == 2
    assert counts[-119.0] == 2


def test_non_overlapping_periods_both_load_fully(con):
    load(con, CARD_1)
    inserted, _ = load(con, CARD_2, "second")
    assert inserted == 13
    assert count(con) == 56


def test_categories_are_assigned_on_insert(con):
    load(con, CARD_1)
    uncategorised = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
    ).fetchone()[0]
    assert uncategorised == 0
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_upsert.py -v`
Expected: FAIL — `AttributeError: module 'server.lib.store' has no attribute 'upsert_transactions'`

- [ ] **Step 8: Append the upsert to store.py**

Add to `server/lib/store.py`:

```python
from collections.abc import Callable, Iterable

from server.lib.ingest.dnb_xlsx import RawRow
from server.lib.ingest.fingerprint import with_identity


def upsert_transactions(
    con: sqlite3.Connection,
    rows: Iterable[RawRow],
    account_id: int,
    account_name: str,
    batch_id: int,
    categoriser: Callable[[str], "object"],
) -> tuple[int, int]:
    """Insert rows that are not already present. Additive and idempotent.

    Returns (inserted, skipped_existing).
    """
    kinds = {r["name"]: r["kind"]
             for r in con.execute("SELECT name, kind FROM categories")}
    ids = {r["name"]: r["id"]
           for r in con.execute("SELECT id, name FROM categories")}

    inserted = skipped = 0
    for row, fp, occurrence in with_identity(list(rows), account_name):
        exists = con.execute(
            "SELECT 1 FROM transactions"
            " WHERE account_id = ? AND fingerprint = ? AND occurrence = ?"
            "   AND is_derived = 0",
            (account_id, fp, occurrence)).fetchone()
        if exists:
            skipped += 1
            continue

        verdict = categoriser(row.description)
        con.execute(
            "INSERT INTO transactions"
            " (date, account_id, description, amount, category_id,"
            "  is_transfer, needs_review, batch_id, source_row,"
            "  fingerprint, occurrence, origin)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,'import')",
            (row.date, account_id, row.description, row.amount,
             ids[verdict.category],
             1 if kinds[verdict.category] == "transfer" else 0,
             1 if verdict.needs_review else 0,
             batch_id, row.source_row, fp, occurrence))
        inserted += 1

    con.commit()
    return inserted, skipped
```

- [ ] **Step 9: Run the whole suite**

Run: `python3 -m pytest -v`
Expected: PASS. All tests from Tasks 1–6.

- [ ] **Step 10: Commit**

```bash
git add server/lib/ingest/fingerprint.py server/lib/store.py \
        db/migrations/003_fingerprint_unique.sql \
        server/test/test_fingerprint.py server/test/test_upsert.py
git commit -m "feat: make ingest additive and idempotent via content fingerprint"
```

---

## Task 7: Budget pool computation

**Files:**
- Create: `server/lib/budget.py`
- Test: `server/test/test_budget_pool.py`

**Interfaces:**
- Consumes: schema from Task 2.
- Produces:
  - `budget.Pool` — frozen dataclass: `income`, `fixed`, `committed`, `savings`, `amount`, `estimated: bool`.
  - `budget.Config` — frozen dataclass: `income_mode`, `fixed_mode`, `manual_income`, `manual_fixed`, `savings_target`, `week_starts_on`.
  - `budget.load_config(con, on_date: datetime.date) -> Config` — newest row with `effective_from <= on_date`.
  - `budget.complete_months(con) -> list[str]` — `YYYY-MM` strings having full coverage.
  - `budget.month_pool(con, month: str, config: Config) -> Pool`

- [ ] **Step 1: Write the failing test**

Create `server/test/test_budget_pool.py`:

```python
import datetime
from pathlib import Path

import pytest

from server.lib import budget, store

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"

CATS = [
    ("Salary", "income", "variable", "settlement"),
    ("Groceries", "expense", "variable", "settlement"),
    ("Mortgage - interest", "expense", "fixed", "settlement"),
    ("Mortgage - principal", "transfer", "variable", "committed"),
    ("Employer loan repayment", "transfer", "variable", "committed"),
    ("Credit card payment", "transfer", "variable", "settlement"),
    ("Internal transfer", "transfer", "variable", "savings"),
]


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.migrate(c, MIGRATIONS)
    c.execute("INSERT INTO accounts (name, kind) VALUES ('Bankkonto','bank')")
    for name, kind, treat, cash in CATS:
        c.execute(
            "INSERT INTO categories (name, kind, budget_treatment, cash_treatment)"
            " VALUES (?,?,?,?)", (name, kind, treat, cash))
    c.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('f', 0, '2026-08-22')")
    c.execute(
        "INSERT INTO budget_config (effective_from, income_mode, fixed_mode,"
        " manual_income, manual_fixed, savings_target)"
        " VALUES ('2026-01-01','manual','manual', 41113.67, 13463.60, 5000.0)")
    c.commit()
    return c


def add(con, date, category, amount, n=[0]):
    n[0] += 1
    cid = con.execute("SELECT id FROM categories WHERE name = ?",
                      (category,)).fetchone()[0]
    kind = con.execute("SELECT kind FROM categories WHERE name = ?",
                       (category,)).fetchone()[0]
    con.execute(
        "INSERT INTO transactions (date, account_id, description, amount,"
        " category_id, is_transfer, batch_id, source_row, fingerprint, occurrence)"
        " VALUES (?,1,?,?,?,?,1,?,?,1)",
        (date, f"row {n[0]}", amount, cid,
         1 if kind == "transfer" else 0, n[0], f"fp{n[0]}"))
    con.commit()


def test_manual_mode_pool_matches_the_spec_worked_example(con):
    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    pool = budget.month_pool(con, "2026-07", cfg)
    assert pool.income == 41113.67
    assert pool.fixed == 13463.60
    assert pool.savings == 5000.0
    assert round(pool.amount, 2) == round(41113.67 - 13463.60 - pool.committed - 5000.0, 2)


def test_committed_transfers_reduce_the_pool(con):
    add(con, "2026-07-20", "Mortgage - principal", -3407.26)
    add(con, "2026-07-27", "Employer loan repayment", -800.0)
    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    pool = budget.month_pool(con, "2026-07", cfg)
    assert pool.committed == 4207.26
    assert round(pool.amount, 2) == 18442.81


def test_settlement_transfers_do_not_reduce_the_pool(con):
    add(con, "2026-07-20", "Credit card payment", -4982.80)
    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    assert budget.month_pool(con, "2026-07", cfg).committed == 0.0


def test_savings_transfers_do_not_reduce_the_pool(con):
    add(con, "2026-07-20", "Internal transfer", -16000.0)
    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    assert budget.month_pool(con, "2026-07", cfg).committed == 0.0


def test_cold_start_falls_back_to_manual_and_marks_estimated(con):
    """No complete calendar month exists, so derived mode must not be used."""
    con.execute("UPDATE budget_config SET income_mode='derived', fixed_mode='derived'")
    con.commit()
    add(con, "2026-07-20", "Salary", 41113.67)
    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    pool = budget.month_pool(con, "2026-07", cfg)
    assert pool.estimated is True
    assert pool.income == 41113.67  # from manual_income, not the single row


def test_config_versioning_picks_the_row_in_force(con):
    con.execute(
        "INSERT INTO budget_config (effective_from, income_mode, fixed_mode,"
        " manual_income, manual_fixed, savings_target)"
        " VALUES ('2026-08-01','manual','manual', 50000.0, 13463.60, 8000.0)")
    con.commit()
    july = budget.load_config(con, datetime.date(2026, 7, 15))
    august = budget.load_config(con, datetime.date(2026, 8, 15))
    assert july.savings_target == 5000.0
    assert august.savings_target == 8000.0


def test_complete_months_excludes_partial_coverage(con):
    add(con, "2026-07-20", "Groceries", -100.0)
    assert "2026-07" not in budget.complete_months(con)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_budget_pool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.lib.budget'`

- [ ] **Step 3: Write the pool half of budget.py**

Create `server/lib/budget.py`:

```python
"""Weekly-envelope budget engine.

The pool is what remains of income after commitments and the savings
target. Commitments are not the same as expenses: mortgage principal is a
transfer (not consumption) yet the cash genuinely leaves, so it must reduce
the pool. Credit card payments must not, because the card's own purchase
lines already carry that spending.
"""
from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass

import sqlite3


@dataclass(frozen=True)
class Config:
    income_mode: str
    fixed_mode: str
    manual_income: float | None
    manual_fixed: float | None
    savings_target: float
    week_starts_on: int


@dataclass(frozen=True)
class Pool:
    income: float
    fixed: float
    committed: float
    savings: float
    amount: float
    estimated: bool


def load_config(con: sqlite3.Connection, on_date: datetime.date) -> Config:
    row = con.execute(
        "SELECT * FROM budget_config WHERE effective_from <= ?"
        " ORDER BY effective_from DESC LIMIT 1",
        (on_date.isoformat(),)).fetchone()
    if row is None:
        raise LookupError(f"no budget_config in force on {on_date}")
    return Config(row["income_mode"], row["fixed_mode"],
                  row["manual_income"], row["manual_fixed"],
                  row["savings_target"], row["week_starts_on"])


def complete_months(con: sqlite3.Connection) -> list[str]:
    """Months with transactions on or before day 1 and on or after the last day.

    A partial month must never feed a trailing average, or the estimate is
    silently low.
    """
    out: list[str] = []
    rows = con.execute(
        "SELECT DISTINCT substr(date, 1, 7) AS m FROM transactions ORDER BY m")
    for row in rows:
        month = row["m"]
        year, mon = int(month[:4]), int(month[5:7])
        last = calendar.monthrange(year, mon)[1]
        first_seen, last_seen = con.execute(
            "SELECT MIN(date), MAX(date) FROM transactions"
            " WHERE substr(date, 1, 7) = ?", (month,)).fetchone()
        if int(first_seen[8:10]) <= 2 and int(last_seen[8:10]) >= last - 1:
            out.append(month)
    return out


def _monthly_average(con: sqlite3.Connection, months: list[str],
                     where: str) -> float:
    if not months:
        return 0.0
    placeholders = ",".join("?" * len(months))
    total = con.execute(
        f"SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM transactions t"
        f" JOIN categories c ON c.id = t.category_id"
        f" WHERE substr(t.date, 1, 7) IN ({placeholders}) AND {where}",
        months).fetchone()[0]
    return round(total / len(months), 2)


def month_pool(con: sqlite3.Connection, month: str, config: Config) -> Pool:
    months = complete_months(con)
    estimated = not months

    if config.income_mode == "derived" and months:
        income = _monthly_average(con, months, "c.kind = 'income'")
    else:
        income = config.manual_income or 0.0

    if config.fixed_mode == "derived" and months:
        fixed = _monthly_average(
            con, months,
            "c.kind = 'expense' AND COALESCE(t.budget_override,"
            " c.budget_treatment) = 'fixed'")
    else:
        fixed = config.manual_fixed or 0.0

    committed = con.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE c.kind = 'transfer' AND c.cash_treatment = 'committed'"
        "   AND substr(t.date, 1, 7) = ?", (month,)).fetchone()[0]
    committed = round(committed, 2)

    amount = round(income - fixed - committed - config.savings_target, 2)
    return Pool(income, fixed, committed, config.savings_target,
                amount, estimated)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_budget_pool.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add server/lib/budget.py server/test/test_budget_pool.py
git commit -m "feat: add budget pool computation with cash treatment handling"
```

---

## Task 8: Envelope and today's figures

**Files:**
- Modify: `server/lib/budget.py` — append envelope functions
- Test: `server/test/test_budget_envelope.py`

**Interfaces:**
- Consumes: `budget.Pool`, `budget.Config`, `budget.month_pool` (Task 7).
- Produces:
  - `budget.week_bounds(day: datetime.date, week_starts_on: int) -> tuple[date, date]`
  - `budget.daily_rate(pools: Mapping[str, Pool], day: datetime.date) -> float`
  - `budget.week_envelope(pools: Mapping[str, Pool], week_start: datetime.date) -> float`
  - `budget.Figures` — frozen dataclass: `week_envelope`, `week_spent`, `week_remaining`, `today_allowance`, `today_spent`, `today_remaining`, `days_left`.
  - `budget.figures(con, day, config, pools) -> Figures`

- [ ] **Step 1: Write the failing test**

Create `server/test/test_budget_envelope.py`:

```python
import datetime

from server.lib import budget

JULY = budget.Pool(41113.67, 13463.60, 4207.26, 5000.0, 18442.81, False)
AUGUST = budget.Pool(41113.67, 13463.60, 0.0, 5000.0, 22650.07, False)
POOLS = {"2026-07": JULY, "2026-08": AUGUST}


def test_week_bounds_monday_start():
    start, end = budget.week_bounds(datetime.date(2026, 7, 15), 1)
    assert start == datetime.date(2026, 7, 13)
    assert end == datetime.date(2026, 7, 19)


def test_daily_rate_divides_pool_by_days_in_that_month():
    rate = budget.daily_rate(POOLS, datetime.date(2026, 7, 15))
    assert round(rate, 2) == round(18442.81 / 31, 2)


def test_week_envelope_sums_seven_daily_rates():
    env = budget.week_envelope(POOLS, datetime.date(2026, 7, 13))
    assert round(env, 2) == 4164.51


def test_week_straddling_month_boundary_uses_each_days_own_rate():
    """Mon 27 Jul - Sun 2 Aug: five July days at 31ths, two August at 31ths."""
    env = budget.week_envelope(POOLS, datetime.date(2026, 7, 27))
    expected = 5 * (18442.81 / 31) + 2 * (22650.07 / 31)
    assert round(env, 2) == round(expected, 2)


def test_today_allowance_excludes_today_spending_from_the_numerator():
    """The trap: dividing week-remaining by days-left reports money already
    spent as still available. Monday, 700 spent today, envelope 4164.51."""
    f = budget.figures_from(envelope=4164.51, spent_before_today=0.0,
                            spent_today=700.0, days_left=7)
    assert round(f.today_allowance, 2) == round(4164.51 / 7, 2)
    assert round(f.today_remaining, 2) == round(4164.51 / 7 - 700.0, 2)
    assert f.today_remaining < 0


def test_tomorrow_recalculates_from_what_is_actually_left():
    f = budget.figures_from(envelope=4164.51, spent_before_today=700.0,
                            spent_today=0.0, days_left=6)
    assert round(f.today_allowance, 2) == round((4164.51 - 700.0) / 6, 2)


def test_underspending_lifts_the_next_days_allowance():
    stingy = budget.figures_from(envelope=4164.51, spent_before_today=100.0,
                                 spent_today=0.0, days_left=6)
    normal = budget.figures_from(envelope=4164.51, spent_before_today=700.0,
                                 spent_today=0.0, days_left=6)
    assert stingy.today_allowance > normal.today_allowance


def test_overspent_week_yields_negative_remaining_not_zero():
    f = budget.figures_from(envelope=4164.51, spent_before_today=4000.0,
                            spent_today=500.0, days_left=2)
    assert f.week_remaining < 0
    assert round(f.week_remaining, 2) == round(4164.51 - 4500.0, 2)


def test_last_day_of_week_divides_by_one():
    f = budget.figures_from(envelope=4164.51, spent_before_today=3000.0,
                            spent_today=0.0, days_left=1)
    assert round(f.today_allowance, 2) == round(4164.51 - 3000.0, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_budget_envelope.py -v`
Expected: FAIL — `AttributeError: module 'server.lib.budget' has no attribute 'week_bounds'`

- [ ] **Step 3: Append the envelope functions**

Add to `server/lib/budget.py`:

```python
from collections.abc import Mapping


@dataclass(frozen=True)
class Figures:
    week_envelope: float
    week_spent: float
    week_remaining: float
    today_allowance: float
    today_spent: float
    today_remaining: float
    days_left: int


def week_bounds(day: datetime.date,
                week_starts_on: int = 1) -> tuple[datetime.date, datetime.date]:
    """week_starts_on: 1 = Monday, matching ISO and Norwegian convention."""
    offset = (day.isoweekday() - week_starts_on) % 7
    start = day - datetime.timedelta(days=offset)
    return start, start + datetime.timedelta(days=6)


def daily_rate(pools: Mapping[str, Pool], day: datetime.date) -> float:
    month = day.strftime("%Y-%m")
    pool = pools.get(month)
    if pool is None:
        return 0.0
    return pool.amount / calendar.monthrange(day.year, day.month)[1]


def week_envelope(pools: Mapping[str, Pool],
                  week_start: datetime.date) -> float:
    """Sum each day's own rate.

    Picking one month's rate for the whole week makes the last week of a
    month disagree with the first week of the next about what a day is worth.
    """
    return round(sum(
        daily_rate(pools, week_start + datetime.timedelta(days=i))
        for i in range(7)), 2)


def figures_from(envelope: float, spent_before_today: float,
                 spent_today: float, days_left: int) -> Figures:
    """Today's allowance is fixed when the day starts.

    Dividing (envelope - spent_including_today) by days_left would report
    money already spent today as still available. Excluding today's spend
    from the numerator while counting today in days_left avoids that: the
    allowance is stable through the day, overspend shows as a negative
    remainder, and tomorrow recalculates from what is genuinely left.
    """
    allowance = (envelope - spent_before_today) / max(days_left, 1)
    week_spent = spent_before_today + spent_today
    return Figures(
        week_envelope=round(envelope, 2),
        week_spent=round(week_spent, 2),
        week_remaining=round(envelope - week_spent, 2),
        today_allowance=round(allowance, 2),
        today_spent=round(spent_today, 2),
        today_remaining=round(allowance - spent_today, 2),
        days_left=days_left)


def _variable_spent(con: sqlite3.Connection, start: str, end: str) -> float:
    """Net variable spending in [start, end]. Income nets against expense."""
    total = con.execute(
        "SELECT COALESCE(SUM(-t.amount), 0) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE t.date >= ? AND t.date <= ? AND t.is_transfer = 0"
        "   AND COALESCE(t.budget_override, c.budget_treatment) = 'variable'",
        (start, end)).fetchone()[0]
    return round(total, 2)


def figures(con: sqlite3.Connection, day: datetime.date, config: Config,
            pools: Mapping[str, Pool]) -> Figures:
    start, end = week_bounds(day, config.week_starts_on)
    envelope = week_envelope(pools, start)
    before = _variable_spent(
        con, start.isoformat(),
        (day - datetime.timedelta(days=1)).isoformat()) if day > start else 0.0
    today = _variable_spent(con, day.isoformat(), day.isoformat())
    return figures_from(envelope, before, today, (end - day).days + 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_budget_envelope.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -v`
Expected: PASS, all tests from Tasks 1–8.

- [ ] **Step 6: Commit**

```bash
git add server/lib/budget.py server/test/test_budget_envelope.py
git commit -m "feat: add weekly envelope and daily allowance calculation"
```

---

## Task 9: Learned rules, corrections migration, reimbursement backfill

**Files:**
- Create: `server/lib/rules.py`
- Create: `db/migrations/004_seed_treatments.sql`
- Test: `server/test/test_rules.py`

**Interfaces:**
- Consumes: `categorise.categorise` (Task 3), schema (Task 2).
- Produces:
  - `rules.learned_map(con) -> dict[str, str]` — pattern → category name, for passing to `categorise`.
  - `rules.teach(con, pattern: str, category: str) -> None` — upsert a merchant rule.
  - `rules.mark_reimbursable(con, transaction_id: int, expected_from: str) -> int` — sets `budget_override='reimbursable'`, creates the `reimbursements` row, returns its id.
  - `rules.outstanding(con) -> list[sqlite3.Row]` — unsettled reimbursements.

- [ ] **Step 1: Write the failing test**

Create `server/test/test_rules.py`:

```python
from pathlib import Path

import pytest

from server.lib import categorise, rules, store

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.migrate(c, MIGRATIONS)
    c.execute("INSERT INTO accounts (name, kind) VALUES ('K','credit_card')")
    for name, kind in categorise.CATEGORIES:
        c.execute("INSERT INTO categories (name, kind) VALUES (?,?)", (name, kind))
    c.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('f',0,'2026-08-22')")
    c.commit()
    return c


def add(con, desc, amount, category="Uncategorised"):
    cid = con.execute("SELECT id FROM categories WHERE name=?",
                      (category,)).fetchone()[0]
    return con.execute(
        "INSERT INTO transactions (date, account_id, description, amount,"
        " category_id, batch_id, source_row, fingerprint, occurrence)"
        " VALUES ('2026-07-31',1,?,?,?,1,2,'fp',1)",
        (desc, amount, cid)).lastrowid


def test_teach_then_learned_map_returns_the_rule(con):
    rules.teach(con, "ecom capital", "Subscriptions")
    assert rules.learned_map(con) == {"ecom capital": "Subscriptions"}


def test_teaching_the_same_pattern_twice_updates_not_duplicates(con):
    rules.teach(con, "ecom capital", "Subscriptions")
    rules.teach(con, "ecom capital", "Entertainment")
    assert rules.learned_map(con) == {"ecom capital": "Entertainment"}
    assert con.execute("SELECT COUNT(*) FROM merchant_rules").fetchone()[0] == 1


def test_learned_rule_changes_categorisation_outcome(con):
    rules.teach(con, "ecom capital", "Subscriptions")
    verdict = categorise.categorise("Visa  100121  Ecom Capital AS",
                                    learned=rules.learned_map(con))
    assert verdict.category == "Subscriptions"


def test_mark_reimbursable_sets_override_and_records_the_debt(con):
    tid = add(con, "Mol*Hoome AS, 4799000000", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")

    row = con.execute(
        "SELECT budget_override FROM transactions WHERE id=?", (tid,)).fetchone()
    assert row["budget_override"] == "reimbursable"

    debt = con.execute("SELECT * FROM reimbursements").fetchone()
    assert debt["expected_from"] == "Nordvest Teknikk AS"
    assert debt["expected_amount"] == 13990.0
    assert debt["settled_at"] is None


def test_reimbursable_row_keeps_its_reporting_category(con):
    """Category is for reporting; the override is what leaves the budget."""
    tid = add(con, "Mol*Hoome AS", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    name = con.execute(
        "SELECT c.name FROM transactions t JOIN categories c"
        " ON c.id=t.category_id WHERE t.id=?", (tid,)).fetchone()[0]
    assert name == "Home & furniture"


def test_outstanding_lists_unsettled_only(con):
    tid = add(con, "Mol*Hoome AS", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    assert len(rules.outstanding(con)) == 1

    con.execute("UPDATE reimbursements SET settled_at='2026-08-06'")
    con.commit()
    assert rules.outstanding(con) == []


def test_seed_migration_sets_fixed_and_exceptional_treatments(con):
    treat = {r["name"]: r["budget_treatment"]
             for r in con.execute("SELECT name, budget_treatment FROM categories")}
    assert treat["Mortgage - interest"] == "fixed"
    assert treat["Student loan"] == "fixed"
    assert treat["Subscriptions"] == "fixed"
    assert treat["Home & furniture"] == "exceptional"
    assert treat["Groceries"] == "variable"


def test_seed_migration_sets_cash_treatments(con):
    cash = {r["name"]: r["cash_treatment"]
            for r in con.execute("SELECT name, cash_treatment FROM categories")}
    assert cash["Mortgage - principal"] == "committed"
    assert cash["Employer loan repayment"] == "committed"
    assert cash["Credit card payment"] == "settlement"
    assert cash["Internal transfer"] == "savings"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.lib.rules'`

- [ ] **Step 3: Write the seed migration**

Categories are inserted by application code, so this migration updates by
name and is a no-op on an empty table — safe in either order.

Create `db/migrations/004_seed_treatments.sql`:

```sql
UPDATE categories SET budget_treatment = 'fixed' WHERE name IN (
    'Mortgage - interest', 'Mortgage - fees', 'Student loan',
    'Utilities - electricity', 'Insurance', 'Gym & fitness', 'Subscriptions');

UPDATE categories SET budget_treatment = 'exceptional' WHERE name IN (
    'Home & furniture', 'Sports & outdoor', 'Memberships');

UPDATE categories SET cash_treatment = 'committed' WHERE name IN (
    'Mortgage - principal', 'Employer loan repayment');

UPDATE categories SET cash_treatment = 'savings' WHERE name IN (
    'Internal transfer');

UPDATE categories SET cash_treatment = 'settlement' WHERE name IN (
    'Credit card payment');
```

- [ ] **Step 4: Write the rules module**

Create `server/lib/rules.py`:

```python
"""Learned categorisation rules and reimbursement tracking.

Replaces the hard-coded CORRECTIONS list from the script era. With additive
ingest there is no rebuild to survive, so a correction is persisted state
rather than code — and taught once, it keeps applying to future statements.
"""
from __future__ import annotations

import datetime
import sqlite3


def learned_map(con: sqlite3.Connection) -> dict[str, str]:
    return {r["pattern"]: r["name"] for r in con.execute(
        "SELECT m.pattern, c.name FROM merchant_rules m"
        " JOIN categories c ON c.id = m.category_id")}


def teach(con: sqlite3.Connection, pattern: str, category: str) -> None:
    cid = con.execute("SELECT id FROM categories WHERE name = ?",
                      (category,)).fetchone()
    if cid is None:
        raise LookupError(f"unknown category: {category}")
    con.execute(
        "INSERT INTO merchant_rules (pattern, category_id, created_at)"
        " VALUES (?, ?, ?)"
        " ON CONFLICT(pattern) DO UPDATE SET category_id = excluded.category_id",
        (pattern.lower(), cid["id"],
         datetime.datetime.now().isoformat(timespec="seconds")))
    con.commit()


def mark_reimbursable(con: sqlite3.Connection, transaction_id: int,
                      expected_from: str, note: str | None = None) -> int:
    row = con.execute("SELECT amount FROM transactions WHERE id = ?",
                      (transaction_id,)).fetchone()
    if row is None:
        raise LookupError(f"no transaction {transaction_id}")

    con.execute(
        "UPDATE transactions SET budget_override = 'reimbursable',"
        " needs_review = 0 WHERE id = ?", (transaction_id,))
    debt = con.execute(
        "INSERT INTO reimbursements"
        " (transaction_id, expected_from, expected_amount, note)"
        " VALUES (?, ?, ?, ?)",
        (transaction_id, expected_from, abs(row["amount"]), note)).lastrowid
    con.commit()
    return debt


def outstanding(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT r.*, t.date, t.description FROM reimbursements r"
        " JOIN transactions t ON t.id = r.transaction_id"
        " WHERE r.settled_at IS NULL ORDER BY t.date"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_rules.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 6: Commit**

```bash
git add server/lib/rules.py db/migrations/004_seed_treatments.sql \
        server/test/test_rules.py
git commit -m "feat: add learned rules and reimbursement tracking"
```

---

## Task 10: CLI and end-to-end reconciliation

**Files:**
- Create: `server/cli.py`
- Test: `server/test/test_cli.py`
- Delete: `db/import_transactions.py`, `db/export.py`, `db/schema.sql`
- Modify: `db/README.md`

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces:
  - `cli.build(db_path, input_dir, migrations_dir) -> dict` — runs the full pipeline, returns `{"inserted", "skipped", "derived", "net", "count"}`.
  - `python3 -m server.cli import --db data/transactions.db`
  - `python3 -m server.cli reconcile --db data/transactions.db`

- [ ] **Step 1: Write the failing test**

Create `server/test/test_cli.py`:

```python
from pathlib import Path

import pytest

from server import cli

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
MIGRATIONS = ROOT / "db" / "migrations"

pytestmark = pytest.mark.skipif(
    not (INPUT / "Kontoutskrift.xlsx").exists(),
    reason="statements not present")


def test_full_pipeline_reproduces_the_known_dataset(tmp_path):
    result = cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    assert result["count"] == 181
    assert result["net"] == 14084.24


def test_pipeline_is_idempotent_across_runs(tmp_path):
    db = tmp_path / "t.db"
    first = cli.build(db, INPUT, MIGRATIONS)
    second = cli.build(db, INPUT, MIGRATIONS)
    assert second["inserted"] == 0
    assert second["skipped"] == first["inserted"]
    assert second["count"] == 181
    assert second["net"] == 14084.24


def test_mortgage_row_is_split_into_three_derived_rows(tmp_path):
    from server.lib import store
    cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    rows = list(con.execute(
        "SELECT c.name, t.amount FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE t.is_derived = 1"))
    assert {r["name"] for r in rows} == {
        "Mortgage - interest", "Mortgage - principal", "Mortgage - fees"}
    assert round(sum(r["amount"] for r in rows), 2) == -13288.75


def test_no_unsplit_mortgage_row_remains(tmp_path):
    from server.lib import store
    cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    assert con.execute(
        "SELECT COUNT(*) FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE c.name = 'Mortgage & loan'"
    ).fetchone()[0] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest server/test/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.cli'`

- [ ] **Step 3: Write the CLI**

Create `server/cli.py`:

```python
"""Command-line entry points for building and checking the database."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from server.lib import categorise, derive, rules, store
from server.lib.ingest import dnb_xlsx

SOURCES = [
    ("Kontoutskrift.xlsx", "Bankkonto", "bank", dnb_xlsx.BANK),
    ("transaksjonsliste(1).xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
    ("transaksjonsliste.xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
]


def _ensure_reference_data(con) -> None:
    for name, kind in categorise.CATEGORIES:
        con.execute(
            "INSERT INTO categories (name, kind) VALUES (?, ?)"
            " ON CONFLICT(name) DO NOTHING", (name, kind))
    for _, account, kind, _ in SOURCES:
        con.execute(
            "INSERT INTO accounts (name, kind) VALUES (?, ?)"
            " ON CONFLICT(name) DO NOTHING", (account, kind))
    con.commit()


def _split_loans(con) -> int:
    """Replace each itemised loan row with its derived parts."""
    ids = {r["name"]: r["id"]
           for r in con.execute("SELECT id, name FROM categories")}
    kinds = {r["name"]: r["kind"]
             for r in con.execute("SELECT name, kind FROM categories")}

    made = 0
    targets = con.execute(
        "SELECT t.id, t.date, t.account_id, t.description, t.amount,"
        " t.batch_id, t.source_row, t.fingerprint FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE c.name = 'Mortgage & loan' AND t.is_derived = 0").fetchall()

    for row in targets:
        parts = derive.split_loan_term(row["description"], row["amount"])
        if not parts:
            continue
        for part in parts:
            con.execute(
                "INSERT INTO transactions (date, account_id, description,"
                " amount, category_id, is_transfer, needs_review, batch_id,"
                " source_row, fingerprint, occurrence, is_derived, origin, note)"
                " VALUES (?,?,?,?,?,?,0,?,?,?,1,1,'derived',?)",
                (row["date"], row["account_id"], part.description, part.amount,
                 ids[part.category],
                 1 if kinds[part.category] == "transfer" else 0,
                 row["batch_id"], row["source_row"], row["fingerprint"],
                 f"split from source row {row['source_row']}"))
            made += 1
        con.execute("DELETE FROM transactions WHERE id = ?", (row["id"],))
    con.commit()
    return made


def build(db_path, input_dir, migrations_dir) -> dict:
    con = store.connect(db_path)
    store.migrate(con, migrations_dir)
    _ensure_reference_data(con)
    store.migrate(con, migrations_dir)   # seed migration needs categories present

    learned = rules.learned_map(con)
    accounts = {r["name"]: r["id"]
                for r in con.execute("SELECT id, name FROM accounts")}
    now = datetime.datetime.now().isoformat(timespec="seconds")

    inserted = skipped = 0
    for filename, account, _kind, layout in SOURCES:
        path = Path(input_dir) / filename
        if not path.exists():
            continue
        rows = dnb_xlsx.read_statement(path, layout)
        batch = con.execute(
            "INSERT INTO import_batches (source_file, row_count, imported_at)"
            " VALUES (?, ?, ?)", (filename, len(rows), now)).lastrowid
        got, dup = store.upsert_transactions(
            con, rows, accounts[account], account, batch,
            lambda d: categorise.categorise(d, learned=learned))
        inserted += got
        skipped += dup

    made = _split_loans(con)

    count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    net = round(con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions").fetchone()[0], 2)
    con.close()
    return {"inserted": inserted, "skipped": skipped, "derived": made,
            "net": net, "count": count}


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="server.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("import", "reconcile"):
        p = sub.add_parser(name)
        p.add_argument("--db", default=str(root / "data" / "transactions.db"))
        p.add_argument("--input", default=str(root / "input"))

    args = parser.parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    result = build(args.db, args.input, root / "db" / "migrations")

    print(f"{result['count']} transactions, net {result['net']:.2f}")
    print(f"  inserted {result['inserted']}, already present {result['skipped']},"
          f" derived {result['derived']}")

    if args.command == "reconcile" and result["net"] != 14084.24:
        print(f"MISMATCH: expected net 14084.24, got {result['net']:.2f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/test/test_cli.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Build the real database and check it by hand**

```bash
python3 -m server.cli reconcile
```

Expected output: `181 transactions, net 14084.24` and exit status 0.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -v`
Expected: PASS, every test from Tasks 1–10.

- [ ] **Step 7: Retire the superseded script**

The script's logic now lives in tested modules. Its `CORRECTIONS` entries are
replaced by `rules.teach` and `rules.mark_reimbursable` calls, so record the
two known ones against the freshly built database:

```bash
python3 - <<'EOF'
from pathlib import Path
from server.lib import rules, store

con = store.connect("data/transactions.db")
gift = con.execute(
    "SELECT id FROM transactions WHERE description LIKE '%Ingvild%Bok%'"
    " AND amount = -166.0").fetchone()
share = con.execute(
    "SELECT id FROM transactions WHERE description LIKE '%Torkel%Bok%'"
    " AND amount = 55.0").fetchone()
gifts = con.execute("SELECT id FROM categories WHERE name='Gifts'").fetchone()[0]
for row in (gift, share):
    con.execute("UPDATE transactions SET category_id=?, needs_review=0,"
                " note='present for mother, split three ways' WHERE id=?",
                (gifts, row["id"]))

phone = con.execute(
    "SELECT id FROM transactions WHERE description LIKE '%Hoome%'").fetchone()
rules.mark_reimbursable(con, phone["id"], "Nordvest Teknikk AS",
                        note="phone paid for by employer")
con.commit()
print("corrections applied")
EOF
```

Then delete the superseded files:

```bash
git rm db/import_transactions.py db/export.py db/schema.sql
```

- [ ] **Step 8: Update the db README**

Rewrite `db/README.md` so it documents the migrations directory and points at
`python3 -m server.cli` instead of the deleted scripts. Keep the "Sources",
"Conventions" and "Categorisation decisions" sections — they are still
accurate and are the only written record of why the rules are shaped as they
are. Replace the "Rebuild" and "Files" sections with:

````markdown
## Rebuild

```bash
python3 -m server.cli import
```

Additive and idempotent — safe to re-run, and re-importing an overlapping
statement period is a no-op. Categorisation rules live in
`server/lib/categorise.py`; per-transaction corrections are persisted in the
`merchant_rules` table via `server/lib/rules.py`, not in code.

## Files

| Path | What it is |
|---|---|
| `db/migrations/` | Numbered SQL migrations, applied in filename order |
| `server/lib/` | Ingest, categorisation, budget engine |
| `server/cli.py` | `import` and `reconcile` commands |
| `data/transactions.db` | The database (gitignored) |
````

- [ ] **Step 9: Verify nothing references the deleted modules**

Run: `grep -rn "import_transactions\|db.export\|db/schema.sql" --include="*.py" --include="*.md" . | grep -v docs/superpowers`
Expected: no output.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: add CLI and retire the standalone import script"
```

---

## Self-Review

**Spec coverage.** Every v1 spec section maps to a task, except the three that belong to later plans:

| Spec section | Task |
|---|---|
| Data model — categories, transactions, transfers | 2 |
| Data model — reimbursements, merchant_rules, budget_config | 2, 9 |
| Budget engine — pool, expected vs actual, cold start | 7 |
| Budget engine — envelope, today's figures, month boundary | 8 |
| Ingest — xlsx parsing | 5 |
| Ingest — additive and idempotent | 6 |
| Ingest — bulk API, manual entry | **Plan 2** (needs HTTP) |
| Refactor of existing importer | 3, 4, 5, 10 |
| Testing — golden file, budget units, idempotency, reconciliation | 3, 7, 8, 6, 10 |
| Migration steps 1–8 | 1, 2, 9, 10 |
| Client | **Plan 3** |
| Auth, networking, Docker | **Plan 2** |

**Deferred deliberately:** `origin='manual'` and `origin='bank'` are in the
schema (Task 2) but nothing writes them in this plan — manual entry arrives
with the API in Plan 2, bank rows with the bank spec. The column exists now
so Plan 2 needs no migration.

**Known gap to resolve in Plan 2:** the four spec open questions (the 835,80
Giro, `MAULUND A/S`, `Ecom Capital AS`, Clothing & shoes treatment) stay as
flagged rows. `rules.teach` is the mechanism for resolving them; no code
change is needed once answered.

**Type consistency checked.** `Verdict` (Task 3) is what `upsert_transactions`
consumes in Task 6 and what `rules` composes with in Task 9. `RawRow` (Task 5)
is the input to `with_identity` (Task 6) and `upsert_transactions`. `Pool` and
`Config` (Task 7) are the inputs to `figures` (Task 8). `DerivedRow` (Task 4)
is consumed only by `cli._split_loans` (Task 10). `categorise.CATEGORIES` is
read by Tasks 6, 9 and 10 fixtures. No name appears with two spellings.

**Assertions verified against real data**, not assumed. Row counts (123 / 43 /
13), the 14 084,24 net, the first bank date, `week_bounds(2026-07-15)` landing
on Monday 13 July, and the 4 164,51 envelope were all executed before this
plan was written. Three were wrong on the first pass and are corrected here:
the salary description has no trailing whitespace once stripped; five rows
match the Proud Mary prefix rather than four, because `Proud Mary Oslo,
Kristiansand` at 259 also matches; and the golden fixture holds 178 rows, not
179, since three derived rows replace one source row.
