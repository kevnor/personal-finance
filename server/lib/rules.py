"""Learned categorisation rules and reimbursement tracking.

Replaces the hard-coded CORRECTIONS list from the script era. With additive
ingest there is no rebuild to survive, so a correction is persisted state
rather than code — and taught once, it keeps applying to future statements.
"""
from __future__ import annotations

import datetime
import sqlite3


def learned_map(con: sqlite3.Connection) -> dict[str, str]:
    return {r["pattern"]: r["name"] for r in con.execute(
        "SELECT m.pattern, c.name FROM merchant_rules m"
        " JOIN categories c ON c.id = m.category_id")}


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
    row = con.execute("SELECT amount FROM transactions WHERE id = ?",
                      (transaction_id,)).fetchone()
    if row is None:
        raise LookupError(f"no transaction {transaction_id}")

    con.execute(
        "UPDATE transactions SET budget_override = 'reimbursable',"
        " needs_review = 0 WHERE id = ?", (transaction_id,))
    debt = con.execute(
        "INSERT INTO reimbursements"
        " (transaction_id, expected_from, expected_amount, note)"
        " VALUES (?, ?, ?, ?)",
        (transaction_id, expected_from, abs(row["amount"]), note)).lastrowid
    con.commit()
    return debt


def outstanding(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT r.*, t.date, t.description FROM reimbursements r"
        " JOIN transactions t ON t.id = r.transaction_id"
        " WHERE r.settled_at IS NULL ORDER BY t.date"))
