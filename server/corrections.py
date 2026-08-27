"""Account-holder corrections that no rule can express.

A memo says what was bought, not why, and a statement line cannot say who
ultimately pays. These two facts came from the account holder during the
2026-08-22 session and were applied once by hand against the database then
on disk -- so a fresh clone plus `import` produced a dataset missing both,
and passed the 181-row / 14 084,24 reconciliation anyway, since neither
correction changes the net. That is exactly the kind of silent divergence
the reconciliation invariant cannot catch, hence this module.

Each correction is keyed on the row's own content (date, description,
amount), not on a row id: ids are assigned by insertion order and mean
nothing across databases. Applying twice is a no-op -- the recategorisation
updates only rows not already in the target category, and
rules.mark_reimbursable upserts.

These are NOT merchant rules. `rules.teach` would be the wrong tool: `Bok`
genuinely does mean Books most of the time, and Hoome genuinely is a
furniture merchant. The correction is about these specific payments.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from server.lib import rules


@dataclass(frozen=True)
class Row:
    """Content key for one transaction."""
    date: str
    description: str
    amount: float


# db/README decision 7. A 166,00 Vipps payment to Ingvild memoed `Bok` bought
# a book as a present for the account holder's mother, split three ways with
# Sindre and Torkel (166 / 3 = 55,33 each). Both the payment and Torkel'
# incoming 55,00 share therefore belong in Gifts, not Books; Sindre' share was
# already memoed `Gave Til Mamma`. Gifts then nets to 56,00 -- the account
# holder's own share -- and Books is empty.
RECATEGORISATIONS: list[tuple[Row, str]] = [
    (Row("2026-07-28",
         "Overføring  9260000000 Ingvild Kvamme Berg BokTpp: Vipps Mobilepay AS",
         -166.0), "Gifts"),
    (Row("2026-07-28",
         "Overføring  92800000000 Torkel Aalborg BokTpp: Vipps",
         55.0), "Gifts"),
]

# db/README decision 8. The 13 990 phone is paid for by the account holder's
# employer, so it is a debt owed rather than a miscategorised expense --
# recorded as a reimbursement, which keeps the category right for reporting
# while budget_override = 'reimbursable' keeps it out of the envelope.
REIMBURSEMENTS: list[tuple[Row, str, str]] = [
    (Row("2026-07-30", "Mol*Hoome AS, 4799000000", -13990.0),
     "Nordvest Teknikk AS", "employer-paid phone"),
]


def _find(con: sqlite3.Connection, row: Row) -> int | None:
    found = con.execute(
        "SELECT id FROM transactions"
        " WHERE date = ? AND description = ? AND amount = ?",
        (row.date, row.description, row.amount)).fetchall()
    if len(found) > 1:
        raise LookupError(
            f"{len(found)} transactions match {row.description!r} on"
            f" {row.date} for {row.amount} -- a correction must name one row")
    return found[0]["id"] if found else None


def apply(con: sqlite3.Connection) -> dict[str, int]:
    """Apply every correction. Idempotent.

    Returns counts: `applied` for corrections that changed something,
    `already` for those already in place, and `missing` for rows not in this
    database (a partial import, say) -- reported rather than raised, since
    corrections are dataset-specific and an incomplete import is a legitimate
    state, but counted so a silent no-op is visible.
    """
    counts = {"applied": 0, "already": 0, "missing": 0}

    for row, category in RECATEGORISATIONS:
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

    for row, expected_from, note in REIMBURSEMENTS:
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
