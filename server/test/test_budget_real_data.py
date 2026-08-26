"""Budget figures measured against the real 181-transaction dataset.

Every other budget test uses hand-built fixtures. Those fixtures never
contained an income row in a week that also had spending, which is exactly
why the salary-netted-into-spending bug survived ten task reviews: the
headline number the app exists to produce was wrong by ~41 000 kr every
payday week and no committed test looked.

The anchors here are the spec's own "Worked example" figures, validated
during design against these same statements.
"""
import datetime
from pathlib import Path

import pytest

from server import cli
from server.lib import budget, store

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
MIGRATIONS = ROOT / "db" / "migrations"

pytestmark = pytest.mark.skipif(
    not (INPUT / "Kontoutskrift.xlsx").exists(),
    reason="statements not present")

# The spec's design figures, i.e. what budget_config is seeded with.
CONFIG = budget.Config(
    income_mode="manual", fixed_mode="manual",
    manual_income=41113.67, manual_fixed=13463.60,
    savings_target=5000.0, week_starts_on=1)


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("real") / "t.db"
    result = cli.build(db, INPUT, MIGRATIONS)
    assert (result["count"], result["net"]) == (181, 14084.24)
    return store.connect(db)


def test_a_freshly_built_database_is_usable_on_first_run(con):
    """load_config raised LookupError on every real database, because nothing
    ever created a budget_config row -- the spec's Cold start section says the
    app is broken on first run without one. CONFIG above is asserted to be
    exactly what import seeds, so the rest of this module measures the real
    configuration rather than a test-local guess."""
    assert budget.load_config(con, datetime.date(2026, 7, 24)) == CONFIG


def week_spent(con, monday: str) -> float:
    start = datetime.date.fromisoformat(monday)
    end = start + datetime.timedelta(days=6)
    return budget._variable_spent(con, start.isoformat(), end.isoformat())


# -- the spec's validated weekly figures ----------------------------------

@pytest.mark.parametrize("monday, expected", [
    ("2026-06-29", 4401.58),   # spec: marginal overspend against 4164.51
    ("2026-07-06", 4358.67),   # spec: the second marginal overspend
])
def test_weekly_variable_spending_matches_the_spec_worked_example(
        con, monday, expected):
    assert week_spent(con, monday) == expected


def test_payday_week_spending_is_positive_and_excludes_the_salary(con):
    """2026-07-17 pays 41 113,67 of salary into a week with 1 858,85 of real
    variable spending. Counting income as negative spending reported
    -39 254,82 -- a week in which the account holder could apparently spend
    43 000 more. Salary is not a grocery refund.
    """
    spent = week_spent(con, "2026-07-13")
    assert spent > 0
    assert spent == 1858.85


def test_employer_reimbursement_does_not_inflate_its_week(con):
    """The +835,80 Giro from Nordvest Teknikk AS is income, not a refund of variable
    spending, so it must not reduce the week it lands in either."""
    assert week_spent(con, "2026-07-20") == 3775.91


def test_figures_on_payday_reports_real_spending(con):
    """figures() is the function the app calls. On 2026-07-24 it previously
    reported today_spent = -257.65 because the same-day 835,80 income row
    outweighed the day's purchases."""
    day = datetime.date(2026, 7, 24)
    pools = {m: budget.month_pool(con, m, CONFIG) for m in ("2026-07", "2026-08")}
    f = budget.figures(con, day, CONFIG, pools)
    assert f.today_spent == 578.15          # was -257.65 (578.15 - 835.80)
    assert f.week_spent == 2418.33          # Mon..Fri of the week, not all 7
    assert f.week_envelope == 4164.51       # the spec's worked-example envelope


# -- the netting the spec mandates must still work ------------------------

def test_the_vy_refund_still_nets_against_public_transport(con):
    """A 320 refund in an expense category is genuine restored budget."""
    with_refund = con.execute(
        "SELECT ROUND(SUM(-t.amount), 2) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE c.name = 'Public transport'").fetchone()[0]
    without_refund = con.execute(
        "SELECT ROUND(SUM(-t.amount), 2) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE c.name = 'Public transport' AND t.amount < 0").fetchone()[0]
    assert round(without_refund - with_refund, 2) == 320.0
    assert week_spent(con, "2026-07-06") == 4358.67  # the week it lands in


@pytest.mark.parametrize("memo_fragment, category, amount", [
    ("MatTpp", "Groceries", 80.0),
    ("IsTpp", "Cafe & bakery", 25.0),
    ("LadingTpp", "Fuel & EV charging", 140.0),
])
def test_incoming_vipps_memo_rows_still_net_against_their_category(
        con, memo_fragment, category, amount):
    row = con.execute(
        "SELECT t.amount, c.name, c.kind,"
        "       COALESCE(t.budget_override, c.budget_treatment) AS treatment"
        " FROM transactions t JOIN categories c ON c.id = t.category_id"
        " WHERE t.description LIKE ? AND t.amount > 0",
        (f"%{memo_fragment}%",)).fetchone()
    assert row is not None
    assert (row["amount"], row["name"]) == (amount, category)
    # An expense category with variable treatment is precisely what
    # _variable_spent counts, so this row nets.
    assert (row["kind"], row["treatment"]) == ("expense", "variable")
