"""Money other people owe -- the Owed screen."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from server.deps import db, db_ro
from server.lib import rules
from server.schemas import ReimbursementIn, ReimbursementOut, SettleIn

router = APIRouter(prefix="/api/reimbursements", tags=["reimbursements"])


def _out(row) -> ReimbursementOut:
    return ReimbursementOut(
        id=row["id"],
        transaction_id=row["transaction_id"],
        date=row["date"],
        description=row["description"],
        expected_from=row["expected_from"],
        expected_amount=row["expected_amount"],
        note=row["note"],
        settled_at=row["settled_at"])


@router.get("", response_model=list[ReimbursementOut])
def list_outstanding(con: sqlite3.Connection = Depends(db_ro)):
    """Debts not yet settled. This is what makes "13 990 owed by the
    employer" a queryable figure rather than a silent exclusion."""
    return [_out(row) for row in rules.outstanding(con)]


@router.post("", response_model=ReimbursementOut,
             status_code=status.HTTP_201_CREATED)
def create(body: ReimbursementIn, con: sqlite3.Connection = Depends(db)):
    """Mark a transaction reimbursable and record the debt.

    Idempotent by transaction: a second call for the same row updates the
    existing debt rather than creating a second one, backed by a UNIQUE index
    so a double-submit can never double the amount owed.
    """
    try:
        debt_id = rules.mark_reimbursable(
            con, body.transaction_id, body.expected_from, body.note)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    row = con.execute(
        "SELECT r.*, t.date, t.description FROM reimbursements r"
        " JOIN transactions t ON t.id = r.transaction_id WHERE r.id = ?",
        (debt_id,)).fetchone()
    return _out(row)


@router.post("/{reimbursement_id}/settle", response_model=ReimbursementOut)
def settle(reimbursement_id: int, body: SettleIn | None = None,
           con: sqlite3.Connection = Depends(db)):
    """Record that the money came back."""
    body = body or SettleIn()
    try:
        row = rules.settle(
            con, reimbursement_id,
            settled_by_transaction_id=body.settled_by_transaction_id,
            settled_at=body.settled_at.isoformat() if body.settled_at else None)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return _out(row)
