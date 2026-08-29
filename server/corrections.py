"""Account-holder corrections that no rule can express.

A memo says what was bought, not why, and a statement line cannot say who
ultimately pays. Facts like that come from the account holder, and they name
specific payments to specific people — so they are the household's data, not
the project's, and they live in the gitignored local file rather than here.
See `server/lib/local.py` for why, and README "Local configuration" for the
format. This module is the mechanism that applies them.

Each correction is keyed on the row's own content (date, description,
amount), not on a row id: ids are assigned by insertion order and mean
nothing across databases. Applying twice is a no-op -- the recategorisation
updates only rows not already in the target category, and
rules.mark_reimbursable upserts.

These are NOT merchant rules. `rules.teach` would be the wrong tool: a memo
reading `Bok` genuinely does mean Books most of the time, and a furniture
shop genuinely is a furniture shop. The correction is about one payment.

They are applied on every import rather than once by hand, because a
correction that changes no amount cannot be noticed missing by the
reconciliation invariant -- which is exactly how the original two went
absent from a rebuilt database while it still reconciled.
"""
from __future__ import annotations

import sqlite3

from server.lib import local, rules

# Kept as aliases so callers and tests have one name for the content key.
Row = local.Correction


def _find(con: sqlite3.Connection, row: Row) -> int | None:
    found = con.execute(
        "SELECT id FROM transactions"
        " WHERE date = ? AND description = ? AND amount = ?",
        (row.date, row.description, row.amount)).fetchall()
    if len(found) > 1:
        raise LookupError(
            f"{len(found)} transactions match this correction's key on"
            f" {row.date} for {row.amount} -- a correction must name one row")
    return found[0]["id"] if found else None


def apply(con: sqlite3.Connection,
          data: local.LocalData | None = None) -> dict[str, int]:
    """Apply every correction in `data`. Idempotent.

    Returns counts: `applied` for corrections that changed something,
    `already` for those already in place, and `missing` for rows not in this
    database (a partial import, say) -- reported rather than raised, since
    corrections are dataset-specific and an incomplete import is a legitimate
    state, but counted so a silent no-op is visible.

    With no data -- a fresh clone with no local file -- this does nothing and
    reports zeroes, which is correct: there is no household attached yet.
    """
    data = data if data is not None else local.EMPTY
    counts = {"applied": 0, "already": 0, "missing": 0}

    for row, category in data.recategorisations:
        transaction_id = _find(con, row)
        if transaction_id is None:
            counts["missing"] += 1
            continue
        cid = con.execute("SELECT id FROM categories WHERE name = ?",
                          (category,)).fetchone()
        if cid is None:
            raise LookupError(f"unknown category: {category}")
        changed = con.execute(
            "UPDATE transactions SET category_id = ?"
            " WHERE id = ? AND category_id IS NOT ?",
            (cid["id"], transaction_id, cid["id"])).rowcount
        counts["applied" if changed else "already"] += 1

    for row, expected_from, note in data.reimbursements:
        transaction_id = _find(con, row)
        if transaction_id is None:
            counts["missing"] += 1
            continue
        before = con.execute(
            "SELECT budget_override FROM transactions WHERE id = ?",
            (transaction_id,)).fetchone()["budget_override"]
        rules.mark_reimbursable(con, transaction_id, expected_from, note)
        counts["applied" if before != "reimbursable" else "already"] += 1

    con.commit()
    return counts
