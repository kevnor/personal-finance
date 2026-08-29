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


def _reference_rows(con):
    con.execute("INSERT INTO accounts (name, kind) VALUES ('Bankkonto','bank')")
    for name, kind in [("Groceries", "expense"), ("Salary", "income"),
                       ("Credit card payment", "transfer"),
                       ("Uncategorised", "expense")]:
        con.execute("INSERT INTO categories (name, kind) VALUES (?,?)",
                    (name, kind))
    con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('f', 0, '2026-08-22')")
    rows = [
        # date, category, amount, is_transfer, needs_review
        ("2026-07-01", "Groceries", -400.0, 0, 0),
        ("2026-07-02", "Groceries", 100.0, 0, 0),    # refund, nets
        ("2026-07-03", "Salary", 41113.67, 0, 0),
        ("2026-07-04", "Credit card payment", -4982.80, 1, 0),
        ("2026-07-05", "Uncategorised", -298.0, 0, 1),
    ]
    for n, (date, category, amount, transfer, review) in enumerate(rows, 1):
        cid = con.execute("SELECT id FROM categories WHERE name = ?",
                          (category,)).fetchone()[0]
        con.execute(
            "INSERT INTO transactions (date, account_id, description, amount,"
            " category_id, is_transfer, needs_review, batch_id, source_row,"
            " fingerprint, occurrence) VALUES (?,1,?,?,?,?,?,1,?,?,1)",
            (date, f"row {n}", amount, cid, transfer, review, n, f"fp{n}"))
    con.commit()


def test_accounting_views_exist(con):
    """001_baseline recreated the deleted schema.sql's tables but not its
    views, so no database this pipeline built had them -- while the spec says
    they are unchanged and three files still reference them."""
    views = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    assert {"v_spending", "v_income", "v_needs_review"} <= views


def test_v_spending_nets_refunds_and_excludes_transfers(con):
    _reference_rows(con)
    spending = {r["category"]: (r["spent"], r["n"])
                for r in con.execute("SELECT * FROM v_spending")}
    assert spending["Groceries"] == (300.0, 2)     # 400 out, 100 back
    assert spending["Uncategorised"] == (298.0, 1)
    assert "Credit card payment" not in spending   # transfer, and not expense
    assert "Salary" not in spending


def test_v_income_reports_income_only(con):
    _reference_rows(con)
    income = [tuple(r) for r in con.execute("SELECT * FROM v_income")]
    assert income == [("Salary", 41113.67, 1)]


def test_v_needs_review_lists_flagged_rows_with_their_guess(con):
    _reference_rows(con)
    flagged = [tuple(r) for r in con.execute("SELECT * FROM v_needs_review")]
    assert flagged == [
        ("2026-07-05", "Bankkonto", "row 5", -298.0, "Uncategorised")]


def test_budget_config_defaults_week_to_monday(con):
    con.execute(
        "INSERT INTO budget_config"
        " (effective_from, income_mode, fixed_mode, savings_target)"
        " VALUES ('2026-01-01', 'manual', 'manual', 5000.0)")
    assert con.execute(
        "SELECT week_starts_on FROM budget_config").fetchone()[0] == 1


# -- checksums and sequence integrity ---------------------------------------

def test_migration_numbers_are_contiguous_with_no_gaps():
    """A gap is a schema-divergence hazard: migrations are skipped by name but
    ordered by filename, so a migration later dropped into a gap runs at a
    different point on a fresh database than on an existing one. 004 was
    skipped once already and is now held by an inert placeholder."""
    numbers = sorted(int(p.name[:3]) for p in MIGRATIONS.glob("*.sql"))
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"migration numbers are not contiguous: {numbers}")


def test_every_migration_is_recorded_with_its_checksum(tmp_path):
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)
    recorded = dict(con.execute(
        "SELECT name, checksum FROM schema_migrations"))
    for path in MIGRATIONS.glob("*.sql"):
        assert recorded[path.name] == store.checksum(
            path.read_text(encoding="utf-8"))


def test_editing_an_applied_migration_is_refused(tmp_path):
    """Silently ignoring the edit is the bad outcome: the change reaches a
    freshly built database and never reaches this one, and the two diverge
    with nothing to show for it."""
    directory = tmp_path / "m"
    directory.mkdir()
    script = directory / "001_x.sql"
    script.write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);\n",
                      encoding="utf-8")

    con = store.connect(tmp_path / "t.db")
    assert store.migrate(con, directory) == ["001_x.sql"]

    script.write_text(
        "CREATE TABLE a (id INTEGER PRIMARY KEY, extra TEXT);\n",
        encoding="utf-8")
    with pytest.raises(store.MigrationError) as exc:
        store.migrate(con, directory)
    assert "001_x.sql" in str(exc.value)


def test_whitespace_only_line_ending_changes_do_not_trip_the_checksum(tmp_path):
    """A file checked out with CRLF endings is the same migration."""
    directory = tmp_path / "m"
    directory.mkdir()
    script = directory / "001_x.sql"
    script.write_text("CREATE TABLE a (id INTEGER);\n", encoding="utf-8")

    con = store.connect(tmp_path / "t.db")
    store.migrate(con, directory)

    script.write_bytes(b"CREATE TABLE a (id INTEGER);\r\n")
    assert store.migrate(con, directory) == []      # no error, nothing to do


def test_a_database_migrated_before_checksums_existed_still_works(tmp_path):
    """Rows recorded by the previous runner carry no checksum. They must be
    left alone rather than read as a mismatch."""
    con = store.connect(tmp_path / "t.db")
    store.migrate(con, MIGRATIONS)
    con.execute("UPDATE schema_migrations SET checksum = NULL")
    con.commit()

    assert store.migrate(con, MIGRATIONS) == []


def test_connection_uses_wal_and_a_busy_timeout(tmp_path):
    """Both are what lets a reader and the writer coexist; under the default
    rollback journal a report running during an import fails outright."""
    con = store.connect(tmp_path / "t.db")
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute(
        "PRAGMA busy_timeout").fetchone()[0] == store.BUSY_TIMEOUT_MS


def test_a_read_only_connection_still_gets_the_busy_timeout(tmp_path):
    """It cannot set journal_mode -- that is a property of the file, set by
    the first writer -- but it must still wait for a lock rather than raise."""
    db = tmp_path / "t.db"
    store.migrate(store.connect(db), MIGRATIONS)
    con = store.connect(db, read_only=True)
    assert con.execute(
        "PRAGMA busy_timeout").fetchone()[0] == store.BUSY_TIMEOUT_MS
