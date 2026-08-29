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
from collections.abc import Iterable, Mapping
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


# Cold-start configuration, from the spec's "Worked example" and "Cold start"
# sections: there is no complete calendar month of data yet (the bank
# statement starts 30 June and the card statements are partial), so both
# modes are manual and switch to derived once a full month exists. The spec
# is explicit that without these seeded figures "the app is broken on first
# run" -- and load_config raises LookupError on an unseeded database, which
# is precisely how it was broken.
DESIGN_CONFIG = {
    "effective_from": "2026-01-01",   # before any statement row (2026-06-10)
    "income_mode": "manual",
    "fixed_mode": "manual",
    "manual_income": 41113.67,        # salary
    "manual_fixed": 13463.60,         # fixed expenses
    "savings_target": 5000.0,         # illustrative pending first-run prompt
    "week_starts_on": 1,              # Monday, ISO and Norwegian convention
}


def seed_default_config(con: sqlite3.Connection,
                        values: Mapping[str, object] | None = None) -> bool:
    """Insert the cold-start budget_config row if none exists at all.

    Returns True if a row was written. Deliberately does nothing when the
    table is non-empty: any existing row is the user's own configuration (or
    a versioned history of it), and re-seeding over that would silently
    revert a changed savings target or salary. Versioning by effective_from
    means past weeks must not recompute.
    """
    if con.execute("SELECT 1 FROM budget_config LIMIT 1").fetchone():
        return False
    values = dict(DESIGN_CONFIG if values is None else values)
    con.execute(
        "INSERT INTO budget_config (effective_from, income_mode, fixed_mode,"
        " manual_income, manual_fixed, savings_target, week_starts_on)"
        " VALUES (:effective_from, :income_mode, :fixed_mode, :manual_income,"
        " :manual_fixed, :savings_target, :week_starts_on)", values)
    con.commit()
    return True


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


# --- assembling the whole picture ------------------------------------------

@dataclass(frozen=True)
class Summary:
    """Everything the home screen needs for one day."""
    day: datetime.date
    week_start: datetime.date
    week_end: datetime.date
    config: Config
    pools: dict[str, Pool]
    figures: Figures

    @property
    def estimated(self) -> bool:
        """True while any month in view is running on a manual figure rather
        than a derived one -- the cold-start state the spec calls out."""
        return any(pool.estimated for pool in self.pools.values())


def months_spanned(week_start: datetime.date) -> list[str]:
    """The `YYYY-MM` keys a week touches -- one, or two across a boundary."""
    return sorted({(week_start + datetime.timedelta(days=i)).strftime("%Y-%m")
                   for i in range(7)})


def pools_for(con: sqlite3.Connection, config: Config,
              months: Iterable[str]) -> dict[str, Pool]:
    return {month: month_pool(con, month, config) for month in months}


def summarise(con: sqlite3.Connection, day: datetime.date) -> Summary:
    """Load the config, build the pools the week needs, and report.

    This is the seam every caller wants: the engine's parts each take a piece
    of state someone else has to assemble, and until now nothing outside the
    tests assembled it -- `month_pool` and `figures` had no production caller
    at all. Building the pool map here is also what keeps `daily_rate` honest:
    it returns 0.0 for a month it has no pool for, so a week straddling a
    month boundary would silently value the days on the far side at nothing
    unless every month the week touches is present.
    """
    config = load_config(con, day)
    week_start, week_end = week_bounds(day, config.week_starts_on)
    pools = pools_for(con, config, months_spanned(week_start))
    return Summary(
        day=day,
        week_start=week_start,
        week_end=week_end,
        config=config,
        pools=pools,
        figures=figures(con, day, config, pools))
