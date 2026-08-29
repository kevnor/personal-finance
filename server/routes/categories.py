"""Categories and their budget treatment."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from server.deps import db, db_ro
from server.lib import categorise, store
from server.schemas import AccountOut, CategoryOut, CategoryPatch

router = APIRouter(prefix="/api/categories", tags=["categories"])
accounts_router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _out(row) -> CategoryOut:
    return CategoryOut(
        label=categorise.LABELS.get(row["name"], row["name"]),
        **dict(row))


@router.get("", response_model=list[CategoryOut])
def list_categories(con: sqlite3.Connection = Depends(db_ro)):
    return [_out(row) for row in store.list_categories(con)]


@router.patch("/{name}", response_model=CategoryOut)
def patch_category(name: str, body: CategoryPatch,
                   con: sqlite3.Connection = Depends(db)):
    """Change a category's default budget treatment.

    The spec calls this out for Clothing & shoes: it is `variable` in v1 but
    plausibly `exceptional`, and moving it is a settings change rather than a
    code change. Addressed by name because that is what the client shows and
    what `categorise.py` produces; ids are an implementation detail.
    """
    try:
        row = store.set_category_treatment(con, name, body.budget_treatment)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return _out(row)


@accounts_router.get("", response_model=list[AccountOut])
def list_accounts(con: sqlite3.Connection = Depends(db_ro)):
    """The accounts a transaction or a statement upload can name.

    The client cannot hardcode these: `POST /api/transactions` and
    `POST /api/imports` both take an account by name and reject an unknown
    one, so the list has to come from the same place that validates it.
    """
    return [AccountOut(**dict(row)) for row in con.execute(
        "SELECT id, name, kind FROM accounts ORDER BY name")]
