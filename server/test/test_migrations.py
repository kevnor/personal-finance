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
