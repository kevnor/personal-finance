"""DB-backed coverage for budget.figures() and budget._variable_spent().

test_budget_envelope.py exercises only the pure-arithmetic half (week_bounds,
daily_rate, week_envelope, figures_from). Nothing there ever touches a
database, so the treatment filter, the transfer exclusion, the income/expense
netting, and the before/today date-range split were previously unverified by
any committed test. These tests close that gap.
"""
import datetime
import itertools
from pathlib import Path

import pytest

from server.lib import budget, store

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"

CATS = [
    ("Salary", "income", "variable", "settlement"),
    ("Groceries", "expense", "variable", "settlement"),
    ("Rent", "expense", "fixed", "settlement"),
    ("Vacation", "expense", "exceptional", "settlement"),
    ("Dining", "expense", "variable", "settlement"),
    ("Mortgage - principal", "transfer", "variable", "committed"),
    ("Employer loan repayment", "transfer", "variable", "committed"),
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
    # Committed transfers so the July pool matches the value already proven
    # in test_budget_pool.py (18442.81) rather than an unfamiliar number.
    c.commit()
    return c


def add(con, date, category, amount, override=None):
    n = next(_counter)
    cid, kind = con.execute(
        "SELECT id, kind FROM categories WHERE name = ?",
        (category,)).fetchone()
    con.execute(
        "INSERT INTO transactions (date, account_id, description, amount,"
        " category_id, is_transfer, budget_override, batch_id, source_row,"
        " fingerprint, occurrence)"
        " VALUES (?,1,?,?,?,?,?,1,?,?,1)",
        (date, f"row {n}", amount, cid,
         1 if kind == "transfer" else 0, override, n, f"fp{n}"))
    con.commit()


def _pools(con, cfg):
    return {"2026-07": budget.month_pool(con, "2026-07", cfg)}


# -- _variable_spent: the treatment/transfer/override filters -------------

def test_fixed_treatment_expense_is_excluded_from_spending(con):
    add(con, "2026-07-15", "Rent", -1000.0)
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 0.0


def test_transfer_is_excluded_even_when_category_treatment_is_variable(con):
    """Internal transfer is budget_treatment='variable' but is_transfer=1;
    is_transfer must win, or savings moves would look like spending."""
    add(con, "2026-07-15", "Internal transfer", -500.0)
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 0.0


def test_exceptional_category_is_excluded_from_spending(con):
    add(con, "2026-07-15", "Vacation", -2000.0)
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 0.0


def test_reimbursable_override_is_excluded_from_spending(con):
    """reimbursable only exists as a per-transaction override (the category
    CHECK constraint does not allow it as a default treatment)."""
    add(con, "2026-07-15", "Dining", -400.0, override="reimbursable")
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 0.0


def test_refund_nets_against_expense_in_the_same_category(con):
    add(con, "2026-07-15", "Groceries", -700.0)
    add(con, "2026-07-15", "Groceries", 100.0)
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 600.0


def test_budget_override_beats_the_category_default(con):
    """Rent defaults to fixed; a per-transaction override of 'variable'
    must still count it as spending."""
    add(con, "2026-07-15", "Rent", -800.0, override="variable")
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 800.0


# -- figures(): the database-backed wrapper --------------------------------

def test_figures_on_first_day_of_week_has_zero_before_and_seven_days_left(con):
    """day == start must not query a backward range at all. A transaction
    dated the day before the week starts proves nothing leaks in."""
    add(con, "2026-07-12", "Groceries", -50.0)
    cfg = budget.load_config(con, datetime.date(2026, 7, 13))
    pools = _pools(con, cfg)
    f = budget.figures(con, datetime.date(2026, 7, 13), cfg, pools)
    assert f.days_left == 7
    assert f.week_spent == 0.0
    envelope = budget.week_envelope(pools, datetime.date(2026, 7, 13))
    assert f.today_allowance == round(envelope / 7, 2)


def test_figures_on_last_day_of_week_has_one_day_left_and_allowance_equals_remaining(con):
    add(con, "2026-07-14", "Groceries", -300.0)
    cfg = budget.load_config(con, datetime.date(2026, 7, 19))
    pools = _pools(con, cfg)
    f = budget.figures(con, datetime.date(2026, 7, 19), cfg, pools)
    assert f.days_left == 1
    assert f.today_allowance == f.week_remaining


def test_figures_splits_before_and_today_spending_correctly(con):
    """Reproduces the scratch-database anchors from the Task 8 review:
    before = 300.0 (a fixed expense and a same-day transfer both excluded),
    today = 600.0 (a 700 expense netted against a 100 refund)."""
    add(con, "2026-07-13", "Groceries", -300.0)
    add(con, "2026-07-14", "Rent", -1000.0)
    add(con, "2026-07-14", "Internal transfer", -500.0)
    add(con, "2026-07-15", "Groceries", -700.0)
    add(con, "2026-07-15", "Groceries", 100.0)

    assert budget._variable_spent(con, "2026-07-13", "2026-07-14") == 300.0
    assert budget._variable_spent(con, "2026-07-15", "2026-07-15") == 600.0

    cfg = budget.load_config(con, datetime.date(2026, 7, 15))
    pools = _pools(con, cfg)
    f = budget.figures(con, datetime.date(2026, 7, 15), cfg, pools)
    assert f.today_spent == 600.0
    assert f.week_spent == 900.0
