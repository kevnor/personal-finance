"""The weekly envelope: the number the whole app is about."""
from __future__ import annotations

import datetime
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from server.deps import db, db_ro, today
from server.lib import budget
from server.schemas import BudgetOut, ConfigIn, ConfigOut, FiguresOut, PoolOut

router = APIRouter(prefix="/api", tags=["budget"])

# 422. Spelled as a literal because starlette renamed the constant
# (HTTP_422_UNPROCESSABLE_ENTITY -> ..._CONTENT) and deprecated the old
# name; the number is the part that is actually stable.
UNPROCESSABLE = 422


@router.get("/budget", response_model=BudgetOut)
def get_budget(day: datetime.date | None = Query(
                   default=None, alias="date",
                   description="the day to report on (default: today)"),
               now: datetime.date = Depends(today),
               con: sqlite3.Connection = Depends(db_ro)):
    """Today's allowance, this week's envelope, and the pools behind them.

    `pools` carries one entry per month the week touches -- two across a
    boundary, where a day on either side is genuinely worth a different
    amount. The client needs them to explain the number, not just show it.
    """
    try:
        summary = budget.summarise(con, day or now)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    return BudgetOut(
        day=summary.day,
        week_start=summary.week_start,
        week_end=summary.week_end,
        estimated=summary.estimated,
        figures=FiguresOut(**vars(summary.figures)),
        pools={month: PoolOut(**vars(pool))
               for month, pool in summary.pools.items()})


@router.get("/budget/config", response_model=ConfigOut)
def get_config(day: datetime.date | None = Query(default=None, alias="date"),
               now: datetime.date = Depends(today),
               con: sqlite3.Connection = Depends(db_ro)):
    """The configuration in force on a date -- today unless asked otherwise."""
    try:
        return ConfigOut(**vars(budget.load_config(con, day or now)))
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.put("/budget/config", response_model=ConfigOut)
def put_config(body: ConfigIn, now: datetime.date = Depends(today),
               con: sqlite3.Connection = Depends(db)):
    """Change the savings target, income mode, or week start.

    Writes a new version rather than editing the current one: past weeks must
    not silently recompute when salary changes. Fields left out keep whatever
    is in force on `effective_from`.
    """
    changes = body.model_dump(exclude={"effective_from"}, exclude_none=True)
    try:
        config = budget.save_config(
            con, body.effective_from or now, **changes)
    except ValueError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc))
    return ConfigOut(**vars(config))
