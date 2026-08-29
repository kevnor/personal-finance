"""Categories and their budget treatment."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from server.deps import db, db_ro
from server.lib import store
from server.schemas import CategoryOut, CategoryPatch

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(con: sqlite3.Connection = Depends(db_ro)):
    return [CategoryOut(**dict(row)) for row in store.list_categories(con)]


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
    return CategoryOut(**dict(row))
