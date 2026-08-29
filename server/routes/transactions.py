"""Listing, hand entry, bulk entry, and corrections."""
from __future__ import annotations

import datetime
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from server.deps import db, db_ro, household
from server.lib import categorise, local, rules, store
from server.schemas import (BulkIn, BulkResult, TransactionIn, TransactionOut,
                            TransactionPatch)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# 422. Spelled as a literal because starlette renamed the constant
# (HTTP_422_UNPROCESSABLE_ENTITY -> ..._CONTENT) and deprecated the old
# name; the number is the part that is actually stable.
UNPROCESSABLE = 422

MAX_PAGE = 500


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    start: datetime.date | None = Query(default=None, alias="from"),
    end: datetime.date | None = Query(default=None, alias="to"),
    needs_review: bool | None = None,
    limit: int = Query(default=200, ge=1, le=MAX_PAGE),
    offset: int = Query(default=0, ge=0),
    con: sqlite3.Connection = Depends(db_ro),
):
    """Transactions newest first. Drives both History and the Review queue.

    `needs_review=true` is the review queue -- the rows whose category is a
    guess -- rather than a separate endpoint, because it is the same list
    with a filter and the client renders it differently.
    """
    rows = store.list_transactions(
        con,
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        needs_review=needs_review,
        limit=limit,
        offset=offset)
    return [TransactionOut.from_row(row) for row in rows]


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int,
                    con: sqlite3.Connection = Depends(db_ro)):
    row = store.get_transaction(con, transaction_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"no transaction {transaction_id}")
    return TransactionOut.from_row(row)


def _insert(con: sqlite3.Connection, body: TransactionIn,
            home: local.LocalData) -> int:
    """Insert one hand-entered row, categorising it if no category was given.

    Running the same `categorise` the importer runs -- learned rules included
    -- is what makes manual entry behave like everything else: typing a
    merchant the user has taught gets that category, not a blank one.
    """
    account_id = store.account_id_for(con, body.account)
    category, needs_review = body.category, False
    if category is None:
        verdict = categorise.categorise(
            body.description, learned=rules.learned_map(con),
            extra_rules=home.rules)
        category, needs_review = verdict.category, verdict.needs_review

    return store.insert_manual(
        con,
        date=body.date.isoformat(),
        description=body.description,
        amount=body.amount,
        account_id=account_id,
        category=category,
        needs_review=needs_review,
        counterparty=body.counterparty,
        note=body.note)


@router.post("", response_model=TransactionOut,
             status_code=status.HTTP_201_CREATED)
def create_transaction(body: TransactionIn,
                       con: sqlite3.Connection = Depends(db),
                       home: local.LocalData = Depends(household)):
    """Add a transaction by hand -- the Add sheet's three-tap path."""
    try:
        new_id = _insert(con, body, home)
    except LookupError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc))
    con.commit()
    return TransactionOut.from_row(store.get_transaction(con, new_id))


@router.post("/bulk", response_model=BulkResult,
             status_code=status.HTTP_201_CREATED)
def create_bulk(body: BulkIn, con: sqlite3.Connection = Depends(db),
                home: local.LocalData = Depends(household)):
    """The spec's programmatic entry point.

    All or nothing: the rows are inserted in one transaction and rolled back
    together if any is rejected. A partial bulk insert is the worst outcome
    here -- the caller cannot tell which rows landed without diffing, and
    re-sending would double the ones that did.
    """
    ids: list[int] = []
    try:
        for row in body.rows:
            ids.append(_insert(con, row, home))
    except LookupError as exc:
        con.rollback()
        raise HTTPException(UNPROCESSABLE, str(exc))
    except Exception:
        con.rollback()
        raise
    con.commit()
    return BulkResult(inserted=len(ids), ids=ids)


@router.patch("/{transaction_id}", response_model=TransactionOut)
def patch_transaction(transaction_id: int, body: TransactionPatch,
                      con: sqlite3.Connection = Depends(db)):
    """Recategorise a row, override its budget treatment, or annotate it.

    With `teach`, the new category is also written to `merchant_rules`, so a
    correction made once keeps applying to future statements -- which is the
    whole point of the table. The pattern defaults to the row's counterparty
    or its description; a caller that knows better can send `teach_pattern`,
    since a full statement description contains dates and reference numbers
    that will never recur verbatim.
    """
    row = store.get_transaction(con, transaction_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"no transaction {transaction_id}")
    try:
        updated = store.update_transaction(
            con, transaction_id,
            category=body.category,
            budget_override=body.budget_override,
            clear_override=body.clear_override,
            note=body.note)
        if body.teach or body.teach_pattern:
            pattern = (body.teach_pattern
                       or row["counterparty"] or row["description"])
            rules.teach(con, pattern, body.category)
    except LookupError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc))
    return TransactionOut.from_row(updated)
