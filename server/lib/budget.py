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
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass


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
        " ORDER BY effective_from DESC, id DESC LIMIT 1",
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
    # Trailing average: only months at or before the target month feed the
    # average, so importing future data never changes a past estimate.
    months = [m for m in complete_months(con) if m <= month]
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

    # Committed transfers are an EXPECTED value like income and fixed, so
    # they must be averaged over the same complete months. Summing the target
    # month's own rows instead made the pool drop the day the mortgage
    # principal posted -- 22650.07 to 19242.81, a ~795 kr/week envelope cut
    # from one row -- which is precisely the mid-month collapse the spec's
    # "Expected vs actual" section warns against.
    committed_where = ("c.kind = 'transfer'"
                       " AND c.cash_treatment = 'committed'")
    if months:
        committed = _monthly_average(con, months, committed_where)
    else:
        # Cold start: no complete month to average. Fall back to the target
        # month's own committed rows, the same shape of fallback income and
        # fixed make to their manual figures -- there is no manual_committed
        # (debt instalments are fixed by contract, so the spec gives them no
        # override), and Pool.estimated is already True on this branch.
        committed = round(con.execute(
            "SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM transactions t"
            " JOIN categories c ON c.id = t.category_id"
            f" WHERE {committed_where} AND substr(t.date, 1, 7) = ?",
            (month,)).fetchone()[0], 2)

    amount = round(income - fixed - committed - config.savings_target, 2)
    return Pool(income, fixed, committed, config.savings_target,
                amount, estimated)


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
    """Net variable spending in [start, end].

    `c.kind = 'expense'` is load-bearing, not decoration. Income categories
    have no income-appropriate value in budget_treatment's CHECK list, so
    Salary inherits the 'variable' default; without this predicate
    SUM(-t.amount) books the salary as ~41 000 of *negative* spending and the
    payday week reports money conjured out of nothing. Netting still works
    where the spec wants it -- an incoming Vipps memoed `Mat` and the VY
    refund both sit in expense categories, so their positive amounts still
    reduce that category's spend.
    """
    total = con.execute(
        "SELECT COALESCE(SUM(-t.amount), 0) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE t.date >= ? AND t.date <= ? AND t.is_transfer = 0"
        "   AND c.kind = 'expense'"
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
