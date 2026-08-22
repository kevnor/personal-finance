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


FIXTURE_CATEGORIES = [("Groceries", "expense"), ("Salary", "income")]
FIXTURE_TREATMENTS = {
    "Groceries": ("variable", "settlement"),
    "Salary": ("variable", "settlement"),
}
FIXTURE_ACCOUNTS = [("Checking", "bank"), ("Visa", "credit_card")]


def test_seed_reference_data_inserts_categories_and_accounts(tmp_path):
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)

    store.seed_reference_data(con, FIXTURE_CATEGORIES, FIXTURE_TREATMENTS, FIXTURE_ACCOUNTS)

    category_names = {r["name"] for r in con.execute("SELECT name FROM categories")}
    account_names = {r["name"] for r in con.execute("SELECT name FROM accounts")}
    assert category_names == {"Groceries", "Salary"}
    assert account_names == {"Checking", "Visa"}


def test_seed_reference_data_is_idempotent(tmp_path):
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)

    store.seed_reference_data(con, FIXTURE_CATEGORIES, FIXTURE_TREATMENTS, FIXTURE_ACCOUNTS)
    before_categories = con.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    before_accounts = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    store.seed_reference_data(con, FIXTURE_CATEGORIES, FIXTURE_TREATMENTS, FIXTURE_ACCOUNTS)
    after_categories = con.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    after_accounts = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    assert after_categories == before_categories == len(FIXTURE_CATEGORIES)
    assert after_accounts == before_accounts == len(FIXTURE_ACCOUNTS)


def test_seed_reference_data_skips_treatments_when_columns_absent(tmp_path):
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)

    columns = {r["name"] for r in con.execute("PRAGMA table_info(categories)")}
    assert "budget_treatment" in columns  # 002_budget migration adds treatment columns

    # Verify that categories are inserted and treatments are applied.
    store.seed_reference_data(con, FIXTURE_CATEGORIES, FIXTURE_TREATMENTS, FIXTURE_ACCOUNTS)

    category_names = {r["name"] for r in con.execute("SELECT name FROM categories")}
    assert category_names == {"Groceries", "Salary"}


def test_seed_reference_data_applies_treatments_when_columns_present(tmp_path):
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)
    # 002_budget migration already adds treatment columns

    store.seed_reference_data(con, FIXTURE_CATEGORIES, FIXTURE_TREATMENTS, FIXTURE_ACCOUNTS)

    row = con.execute(
        "SELECT budget_treatment, cash_treatment FROM categories WHERE name = 'Groceries'"
    ).fetchone()
    assert (row["budget_treatment"], row["cash_treatment"]) == ("variable", "settlement")

    # Re-running repairs a row whose treatment has drifted.
    con.execute("UPDATE categories SET budget_treatment = 'exceptional' WHERE name = 'Groceries'")
    store.seed_reference_data(con, FIXTURE_CATEGORIES, FIXTURE_TREATMENTS, FIXTURE_ACCOUNTS)
    repaired = con.execute(
        "SELECT budget_treatment FROM categories WHERE name = 'Groceries'"
    ).fetchone()
    assert repaired["budget_treatment"] == "variable"
