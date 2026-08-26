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
        " ORDER BY effective_from DESC LIMIT 1",
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
    months = complete_months(con)
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

    committed = con.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE c.kind = 'transfer' AND c.cash_treatment = 'committed'"
        "   AND substr(t.date, 1, 7) = ?", (month,)).fetchone()[0]
    committed = round(committed, 2)

    amount = round(income - fixed - committed - config.savings_target, 2)
    return Pool(income, fixed, committed, config.savings_target,
                amount, estimated)
