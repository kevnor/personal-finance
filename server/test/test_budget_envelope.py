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
