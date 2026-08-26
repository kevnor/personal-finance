import datetime
import itertools
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

_counter = itertools.count(1)


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


def add(con, date, category, amount):
    n = next(_counter)
    cid = con.execute("SELECT id FROM categories WHERE name = ?",
                      (category,)).fetchone()[0]
    kind = con.execute("SELECT kind FROM categories WHERE name = ?",
                       (category,)).fetchone()[0]
    con.execute(
        "INSERT INTO transactions (date, account_id, description, amount,"
        " category_id, is_transfer, batch_id, source_row, fingerprint, occurrence)"
        " VALUES (?,1,?,?,?,?,1,?,?,1)",
        (date, f"row {n}", amount, cid,
         1 if kind == "transfer" else 0, n, f"fp{n}"))
    con.commit()


def test_manual_mode_pool_matches_the_spec_worked_example(con):
    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    pool = budget.month_pool(con, "2026-07", cfg)
    assert pool.income == 41113.67
    assert pool.fixed == 13463.60
    assert pool.savings == 5000.0
    assert pool.committed == 0.0
    assert pool.amount == 22650.07


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


def test_derived_average_excludes_months_after_the_target(con):
    """The trailing average must not look forward.

    A complete September must never feed a pool computed for January, even
    though both are 'complete' months in the data — otherwise importing
    future statements would silently change a past estimate, and asking for
    the same past month again later could give a different answer.
    """
    con.execute("UPDATE budget_config SET income_mode='derived'")
    con.commit()
    add(con, "2026-01-01", "Salary", 5000.0)
    add(con, "2026-01-31", "Salary", 5000.01)
    add(con, "2026-09-01", "Salary", 50000.0)
    add(con, "2026-09-29", "Salary", 50000.01)
    cfg = budget.load_config(con, datetime.date(2026, 1, 15))
    pool = budget.month_pool(con, "2026-01", cfg)
    assert pool.estimated is False
    assert pool.income == 10000.01


def test_load_config_breaks_ties_on_same_effective_from(con):
    """A same-day correction must win over the row it corrects.

    Two budget_config rows sharing an effective_from date represent someone
    fixing a mistake the same day, not two independent versions — the most
    recently inserted row must be picked, not an arbitrary one.
    """
    con.execute(
        "INSERT INTO budget_config (effective_from, income_mode, fixed_mode,"
        " manual_income, manual_fixed, savings_target)"
        " VALUES ('2026-01-01','manual','manual', 9999.0, 13463.60, 5000.0)")
    con.commit()
    cfg = budget.load_config(con, datetime.date(2026, 1, 15))
    assert cfg.manual_income == 9999.0
