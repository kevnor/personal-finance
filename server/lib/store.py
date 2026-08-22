"""Persistence: connections, migrations, and transaction writes."""
from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from server.lib.ingest.dnb_xlsx import RawRow
from server.lib.ingest.fingerprint import with_identity


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def migrate(con: sqlite3.Connection, migrations_dir: str | Path) -> list[str]:
    """Apply every unapplied migration in filename order. Returns names applied."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r["name"] for r in con.execute("SELECT name FROM schema_migrations")}

    applied: list[str] = []
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        if path.name in done:
            continue
        con.executescript(path.read_text(encoding="utf-8"))
        con.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (path.name, now))
        applied.append(path.name)
    con.commit()
    return applied


def seed_reference_data(
    con: sqlite3.Connection,
    categories: Iterable[tuple[str, str]],
    treatments: Mapping[str, tuple[str, str]],
    accounts: Iterable[tuple[str, str]],
) -> None:
    """Insert reference categories/accounts and apply category treatments.

    Idempotent: inserts are ON CONFLICT(name) DO NOTHING, and treatment
    updates are safe to repeat. Treatment columns (budget_treatment,
    cash_treatment) are optional — added by a later migration — so they
    are only updated when present on the categories table.
    """
    con.executemany(
        "INSERT INTO categories (name, kind) VALUES (?, ?) "
        "ON CONFLICT(name) DO NOTHING",
        list(categories))
    con.executemany(
        "INSERT INTO accounts (name, kind) VALUES (?, ?) "
        "ON CONFLICT(name) DO NOTHING",
        list(accounts))

    columns = {row["name"] for row in con.execute("PRAGMA table_info(categories)")}
    if "budget_treatment" in columns and "cash_treatment" in columns:
        con.executemany(
            "UPDATE categories SET budget_treatment = ?, cash_treatment = ? "
            "WHERE name = ?",
            [(budget, cash, name) for name, (budget, cash) in treatments.items()])

    con.commit()


def upsert_transactions(
    con: sqlite3.Connection,
    rows: Iterable[RawRow],
    account_id: int,
    account_name: str,
    batch_id: int,
    categoriser: Callable[[str], "object"],
) -> tuple[int, int]:
    """Insert rows that are not already present. Additive and idempotent.

    Returns (inserted, skipped_existing).
    """
    kinds = {r["name"]: r["kind"]
             for r in con.execute("SELECT name, kind FROM categories")}
    ids = {r["name"]: r["id"]
           for r in con.execute("SELECT id, name FROM categories")}

    inserted = skipped = 0
    for row, fp, occurrence in with_identity(list(rows), account_name):
        exists = con.execute(
            "SELECT 1 FROM transactions"
            " WHERE account_id = ? AND fingerprint = ? AND occurrence = ?"
            "   AND is_derived = 0",
            (account_id, fp, occurrence)).fetchone()
        if exists:
            skipped += 1
            continue

        verdict = categoriser(row.description)
        con.execute(
            "INSERT INTO transactions"
            " (date, account_id, description, amount, category_id,"
            "  is_transfer, needs_review, batch_id, source_row,"
            "  fingerprint, occurrence, origin)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,'import')",
            (row.date, account_id, row.description, row.amount,
             ids[verdict.category],
             1 if kinds[verdict.category] == "transfer" else 0,
             1 if verdict.needs_review else 0,
             batch_id, row.source_row, fp, occurrence))
        inserted += 1

    con.commit()
    return inserted, skipped
