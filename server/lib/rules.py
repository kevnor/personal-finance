"""Learned categorisation rules and reimbursement tracking.

Replaces the hard-coded CORRECTIONS list from the script era. With additive
ingest there is no rebuild to survive, so a correction is persisted state
rather than code — and taught once, it keeps applying to future statements.
"""
from __future__ import annotations

import datetime
import sqlite3


def learned_map(con: sqlite3.Connection) -> dict[str, str]:
    """pattern -> category name, longest pattern first.

    `categorise` takes the first matching key in iteration order (a plain
    dict preserves insertion order), so when two taught patterns both
    substring-match a description, ordering by length here guarantees the
    more specific teaching wins deterministically.
    """
    return {r["pattern"]: r["name"] for r in con.execute(
        "SELECT m.pattern, c.name FROM merchant_rules m"
        " JOIN categories c ON c.id = m.category_id"
        " ORDER BY length(m.pattern) DESC")}


def teach(con: sqlite3.Connection, pattern: str, category: str) -> None:
    cid = con.execute("SELECT id FROM categories WHERE name = ?",
                      (category,)).fetchone()
    if cid is None:
        raise LookupError(f"unknown category: {category}")
    con.execute(
        "INSERT INTO merchant_rules (pattern, category_id, created_at)"
        " VALUES (?, ?, ?)"
        " ON CONFLICT(pattern) DO UPDATE SET category_id = excluded.category_id",
        (pattern.lower(), cid["id"],
         datetime.datetime.now().isoformat(timespec="seconds")))
    con.commit()


def mark_reimbursable(con: sqlite3.Connection, transaction_id: int,
                      expected_from: str, note: str | None = None) -> int:
    """Mark a transaction as reimbursable and record (or refresh) the debt.

    Idempotent: a second call for the same transaction_id updates the
    existing reimbursements row (expected_from/expected_amount/note)
    instead of creating a duplicate -- a UNIQUE index on transaction_id
    backs this at the schema level too, so a retry or double-submit can
    never double the amount owed. Recording a debt says nothing about
    whether the category is correct, so needs_review is left untouched;
    it is cleared by recategorising, not by this.
    """
    row = con.execute("SELECT amount FROM transactions WHERE id = ?",
                      (transaction_id,)).fetchone()
    if row is None:
        raise LookupError(f"no transaction {transaction_id}")

    con.execute(
        "UPDATE transactions SET budget_override = 'reimbursable'"
        " WHERE id = ?", (transaction_id,))
    con.execute(
        "INSERT INTO reimbursements"
        " (transaction_id, expected_from, expected_amount, note)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(transaction_id) DO UPDATE SET"
        "   expected_from = excluded.expected_from,"
        "   expected_amount = excluded.expected_amount,"
        "   note = excluded.note",
        (transaction_id, expected_from, abs(row["amount"]), note))
    debt_id = con.execute(
        "SELECT id FROM reimbursements WHERE transaction_id = ?",
        (transaction_id,)).fetchone()["id"]
    con.commit()
    return debt_id


def outstanding(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT r.*, t.date, t.description FROM reimbursements r"
        " JOIN transactions t ON t.id = r.transaction_id"
        " WHERE r.settled_at IS NULL ORDER BY t.date"))
