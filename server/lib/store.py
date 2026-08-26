"""Persistence: connections, migrations, and transaction writes."""
from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from server.lib.ingest import RawRow
from server.lib.ingest.fingerprint import with_identity


class LegacyDataError(RuntimeError):
    """The database holds imported rows that predate content fingerprints."""


def connect(path: str | Path, read_only: bool = False) -> sqlite3.Connection:
    """Open the database. `read_only` opens it via SQLite's mode=ro URI.

    A read-only connection is what makes a reporting command's promise not to
    mutate enforceable rather than merely intended: any write raises
    sqlite3.OperationalError. mode=ro also refuses to create a missing file,
    so callers should check existence first to give a useful message.
    """
    if read_only:
        con = sqlite3.connect(
            f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    else:
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


def require_fingerprinted_imports(con: sqlite3.Connection) -> None:
    """Refuse to import into a database holding unfingerprinted import rows.

    Migration 002 backfills fingerprint = '' for rows that predate content
    identity, and 003's partial unique index deliberately excludes them. So
    upsert_transactions can match none of them and re-importing the same
    statements silently DOUBLES the dataset -- 362 rows, net 28168.48,
    stably wrong across repeated runs.

    A wrong number that stabilises is the worst failure mode this codebase
    has, so this fails loudly rather than backfilling quietly: a silent
    repair would have to guess each legacy row's account_key and occurrence,
    and getting that wrong reproduces the duplication with no trace.
    """
    stale = con.execute(
        "SELECT COUNT(*) FROM transactions"
        " WHERE origin = 'import' AND fingerprint = ''").fetchone()[0]
    if stale:
        raise LegacyDataError(
            f"{stale} imported transactions have no content fingerprint, so"
            " importing would insert every statement row a second time"
            " instead of recognising it (expect roughly double the rows and"
            " double the net). This database predates fingerprint identity"
            " -- most likely a copy of the original hand-built"
            " db/transactions.db, now kept as data/legacy-2026-08-22.db."
            " Import into a database built by `python3 -m server.cli import`"
            " instead, or backfill fingerprint and occurrence for the"
            " existing rows first.")


def upsert_transactions(
    con: sqlite3.Connection,
    rows: Iterable[RawRow],
    account_id: int,
    batch_id: int,
    categoriser: Callable[[str], "object"],
    counterparty: Callable[[str], str | None] | None = None,
) -> tuple[int, int]:
    """Insert rows that are not already present. Additive and idempotent.

    Identity is scoped by account_id, not by the account's (mutable)
    display name — renaming an account must not re-duplicate its history.

    `counterparty(description)` extracts the other party's name (a Vipps
    recipient, say) for the counterparty column. Injected like `categoriser`
    rather than imported, because that extraction is text semantics and this
    module is persistence; when omitted the column is left NULL.

    Returns (inserted, skipped_existing).
    """
    kinds = {r["name"]: r["kind"]
             for r in con.execute("SELECT name, kind FROM categories")}
    ids = {r["name"]: r["id"]
           for r in con.execute("SELECT id, name FROM categories")}

    account_key = str(account_id)
    inserted = skipped = 0
    for row, fp, occurrence in with_identity(list(rows), account_key):
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
            "  fingerprint, occurrence, counterparty, origin)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'import')",
            (row.date, account_id, row.description, row.amount,
             ids[verdict.category],
             1 if kinds[verdict.category] == "transfer" else 0,
             1 if verdict.needs_review else 0,
             batch_id, row.source_row, fp, occurrence,
             counterparty(row.description) if counterparty else None))
        inserted += 1

    con.commit()
    return inserted, skipped


def insert_derived_rows(
    con: sqlite3.Connection,
    rows: Iterable[RawRow],
    account_id: int,
    batch_id: int,
    splitter: Callable[[str, float], list],
) -> tuple[int, int, int]:
    """Insert derived rows for source rows that split (e.g. a loan term into
    interest/principal/fee parts), skipping any source row already split.

    Shares upsert_transactions' fingerprint/occurrence identity scheme, but
    checks it against is_derived = 1 rather than is_derived = 0. Migration
    003's partial unique index deliberately excludes derived rows -- one
    source row legitimately produces several of them -- so this in-code
    check, not a database constraint, is what keeps a repeat run from
    duplicating a split. Splitting before insertion (rather than inserting
    the source row plainly and later deleting it in favour of its parts) is
    what keeps that check meaningful: a deleted is_derived = 0 row would be
    invisible to upsert_transactions' own identity check above, and the
    next run would silently reinsert and resplit it.

    `splitter(description, amount)` returns the parts to insert for one
    source row, or an empty list for a row that does not split -- such rows
    are left untouched, since they belong to the normal upsert_transactions
    path instead.

    Returns (inserted, skipped, derived): inserted/skipped are counted in
    *source rows*, like upsert_transactions, so the two still sum to
    len(rows); derived is the total count of derived rows actually written,
    reported separately since one source row can produce several.
    """
    ids = {r["name"]: r["id"]
           for r in con.execute("SELECT id, name FROM categories")}
    kinds = {r["name"]: r["kind"]
             for r in con.execute("SELECT name, kind FROM categories")}

    account_key = str(account_id)
    inserted = skipped = derived = 0
    for row, fp, occurrence in with_identity(list(rows), account_key):
        parts = splitter(row.description, row.amount)
        if not parts:
            continue

        exists = con.execute(
            "SELECT 1 FROM transactions"
            " WHERE account_id = ? AND fingerprint = ? AND occurrence = ?"
            "   AND is_derived = 1",
            (account_id, fp, occurrence)).fetchone()
        if exists:
            skipped += 1
            continue

        for part in parts:
            con.execute(
                "INSERT INTO transactions (date, account_id, description,"
                " amount, category_id, is_transfer, needs_review, batch_id,"
                " source_row, fingerprint, occurrence, is_derived, origin, note)"
                " VALUES (?,?,?,?,?,?,0,?,?,?,?,1,'derived',?)",
                (row.date, account_id, part.description, part.amount,
                 ids[part.category],
                 1 if kinds[part.category] == "transfer" else 0,
                 batch_id, row.source_row, fp, occurrence,
                 f"split from source row {row.source_row}"))
            derived += 1
        inserted += 1

    con.commit()
    return inserted, skipped, derived
