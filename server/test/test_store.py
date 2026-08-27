import sqlite3
from pathlib import Path

import pytest

from server.lib import store
from server.lib import ingest
from server.lib.ingest import dnb_xlsx, fingerprint

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
SERVER = Path(__file__).resolve().parents[1]


def test_raw_row_is_owned_by_the_ingest_package_not_the_dnb_reader():
    """The spec's ingest design rests on four sources sharing one row shape,
    so the shape cannot belong to one format's reader. It previously did, and
    both store.py and fingerprint.py imported the persistence and identity
    layers' central type from a DNB spreadsheet parser."""
    assert dnb_xlsx.RawRow is ingest.RawRow      # still importable there
    assert ingest.RawRow.__module__ == "server.lib.ingest"


def test_the_persistence_and_identity_layers_do_not_import_a_format_reader():
    for module in ("lib/store.py", "lib/ingest/fingerprint.py"):
        source = (SERVER / module).read_text(encoding="utf-8")
        assert "dnb_xlsx" not in source, module
    assert fingerprint.RawRow is ingest.RawRow


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


def _migrations_with(tmp_path, name, sql):
    """A migrations directory holding 001_baseline plus one extra script."""
    directory = tmp_path / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "001_baseline.sql").write_text(
        (MIGRATIONS / "001_baseline.sql").read_text(encoding="utf-8"),
        encoding="utf-8")
    (directory / name).write_text(sql, encoding="utf-8")
    return directory


def test_a_failing_migration_is_rolled_back_whole(tmp_path):
    """A mid-script failure used to leave the statements before it applied
    (SQLite autocommits each one) but unrecorded, so every later migrate()
    re-ran the script and died on `duplicate column name` -- unrecoverable
    without hand surgery. Each script must apply or not at all."""
    directory = _migrations_with(
        tmp_path, "002_half_bad.sql",
        "ALTER TABLE categories ADD COLUMN half_applied TEXT;\n"
        "THIS IS NOT VALID SQL;\n")
    con = store.connect(tmp_path / "t.db")

    with pytest.raises(sqlite3.OperationalError):
        store.migrate(con, directory)

    columns = {r["name"] for r in con.execute("PRAGMA table_info(categories)")}
    assert "half_applied" not in columns
    recorded = {r["name"] for r in con.execute(
        "SELECT name FROM schema_migrations")}
    assert recorded == {"001_baseline.sql"}   # the script that did succeed


def test_migrate_recovers_once_a_failing_script_is_fixed(tmp_path):
    """The recovery the old behaviour denied: fix the script, run again."""
    directory = _migrations_with(
        tmp_path, "002_half_bad.sql",
        "ALTER TABLE categories ADD COLUMN half_applied TEXT;\n"
        "THIS IS NOT VALID SQL;\n")
    con = store.connect(tmp_path / "t.db")
    with pytest.raises(sqlite3.OperationalError):
        store.migrate(con, directory)

    (directory / "002_half_bad.sql").write_text(
        "ALTER TABLE categories ADD COLUMN half_applied TEXT;\n",
        encoding="utf-8")
    assert store.migrate(con, directory) == ["002_half_bad.sql"]
    columns = {r["name"] for r in con.execute("PRAGMA table_info(categories)")}
    assert "half_applied" in columns


def test_a_script_and_its_migration_record_commit_together(tmp_path):
    """The record cannot lag the DDL: a script that succeeds is recorded in
    the same transaction, so there is no window where a crash leaves applied
    DDL unrecorded."""
    directory = _migrations_with(
        tmp_path, "002_ok.sql",
        "ALTER TABLE categories ADD COLUMN extra TEXT;\n")
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, directory)

    # Read through a second connection: only committed state is visible.
    other = store.connect(tmp_path / "t.db")
    assert {r["name"] for r in other.execute(
        "SELECT name FROM schema_migrations")} == {
            "001_baseline.sql", "002_ok.sql"}
    assert "extra" in {r["name"] for r in other.execute(
        "PRAGMA table_info(categories)")}


def test_a_migration_name_with_a_quote_is_recorded_safely(tmp_path):
    """The migration name is inlined into the script (executescript takes no
    parameters), so it must be quoted rather than concatenated raw."""
    directory = _migrations_with(
        tmp_path, "002_it's fine.sql",
        "ALTER TABLE categories ADD COLUMN quoted TEXT;\n")
    con = store.connect(tmp_path / "t.db")
    assert "002_it's fine.sql" in store.migrate(con, directory)
    assert {r["name"] for r in con.execute(
        "SELECT name FROM schema_migrations")} == {
            "001_baseline.sql", "002_it's fine.sql"}
    assert store.migrate(con, directory) == []   # still idempotent


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
    # Test that seed_reference_data gracefully handles schema without treatment columns.
    # Create a migrations directory containing only 001_baseline.sql (001 applied, 002 not).
    baseline_migrations = tmp_path / "baseline_migrations"
    baseline_migrations.mkdir()
    (baseline_migrations / "001_baseline.sql").write_text(
        (MIGRATIONS / "001_baseline.sql").read_text(encoding="utf-8"),
        encoding="utf-8")

    con = store.connect(tmp_path / "t.db")
    store.migrate(con, baseline_migrations)

    columns = {r["name"] for r in con.execute("PRAGMA table_info(categories)")}
    assert "budget_treatment" not in columns  # baseline schema has no treatment columns yet

    # Must not raise even though the treatment columns don't exist.
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
