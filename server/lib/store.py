"""Persistence: connections, migrations, and transaction writes."""
from __future__ import annotations

import datetime
import hashlib
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from server.lib.ingest import RawRow
from server.lib.ingest.fingerprint import with_identity


class LegacyDataError(RuntimeError):
    """The database holds imported rows that predate content fingerprints."""


class MigrationError(RuntimeError):
    """A migration file no longer matches the one that was applied."""


# How long a connection waits for a lock it cannot take immediately, rather
# than raising `database is locked` at once. The default is 0.
BUSY_TIMEOUT_MS = 5000


def connect(path: str | Path, read_only: bool = False,
            same_thread: bool = True) -> sqlite3.Connection:
    """Open the database. `read_only` opens it via SQLite's mode=ro URI.

    A read-only connection is what makes a reporting command's promise not to
    mutate enforceable rather than merely intended: any write raises
    sqlite3.OperationalError. mode=ro also refuses to create a missing file,
    so callers should check existence first to give a useful message.

    Two settings matter once anything but the CLI opens this file. WAL lets a
    reader and the writer work at the same time -- under the default rollback
    journal they block each other, so a report running while an import writes
    fails outright. And `busy_timeout` makes a connection wait for a lock
    instead of raising `database is locked` the instant it meets one. Neither
    changes behaviour for a single CLI process; both are what the planned
    HTTP server will need, and setting them here means it inherits them
    rather than rediscovering the problem under concurrent requests.

    journal_mode is a property of the database file, not of the connection,
    so it is set once by whichever writer opens it first and persists. A
    read-only connection cannot set it, and does not need to.

    `same_thread=False` lifts sqlite3's own check that a connection is only
    used by the thread that opened it. The HTTP layer needs it and the CLI
    does not, so it is opt-in: under a real ASGI server a sync dependency's
    setup, the route handler and the dependency's teardown each run on
    whichever threadpool worker is free, so one request's connection is
    legitimately touched by three different threads -- sequentially, never
    concurrently, since each step awaits the last. Python's sqlite3 is built
    in serialized mode (`sqlite3.threadsafety == 3`), so even the concurrent
    case would be safe; the check is what stops us, not the library.

    Leaving it on by default keeps the check as a real guard everywhere it
    costs nothing: a connection genuinely shared between requests would still
    be a bug, and the CLI has no threads to confuse.
    """
    if read_only:
        con = sqlite3.connect(
            f"{Path(path).resolve().as_uri()}?mode=ro", uri=True,
            check_same_thread=same_thread)
    else:
        con = sqlite3.connect(str(path), check_same_thread=same_thread)
        con.execute("PRAGMA journal_mode = WAL")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return con


def _sql_literal(value: str) -> str:
    """Quote a string for embedding in a script.

    executescript takes no parameters, and the migration's record has to live
    inside the same transaction as its DDL, so this one value is inlined.
    """
    return "'" + value.replace("'", "''") + "'"


def checksum(script: str) -> str:
    """Content hash of a migration, ignoring line-ending differences."""
    return hashlib.sha256(
        "\n".join(script.splitlines()).encode("utf-8")).hexdigest()[:16]


def migrate(con: sqlite3.Connection, migrations_dir: str | Path) -> list[str]:
    """Apply every unapplied migration in filename order. Returns names applied.

    Each script runs in its own transaction, together with the row recording
    it, and is rolled back as a unit if any statement fails. Without that, a
    mid-script failure left the statements before it applied (SQLite
    autocommits each one) but unrecorded, so every later migrate() re-ran the
    script and died on `duplicate column name` with no recovery short of hand
    surgery on the schema. DDL is transactional in SQLite, which is what
    makes the rollback complete.

    BEGIN and COMMIT are part of the script text on purpose: executescript
    commits any pending transaction before it runs, so a transaction opened
    around the call would be discarded rather than honoured.

    Each applied migration's content hash is recorded and re-checked on every
    run. Editing a migration that has already been applied is otherwise
    silently ignored forever -- the file is skipped by name, so the change
    reaches a fresh database and never reaches an existing one, and the two
    diverge with nothing to show for it. `MigrationError` says so instead.
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    # Added after the fact, so a database migrated before checksums existed
    # keeps working: its rows carry NULL and are not verified.
    columns = {r["name"] for r in con.execute(
        "PRAGMA table_info(schema_migrations)")}
    if "checksum" not in columns:
        con.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT")
    con.commit()

    done = {r["name"]: r["checksum"]
            for r in con.execute(
                "SELECT name, checksum FROM schema_migrations")}

    applied: list[str] = []
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        script_text = path.read_text(encoding="utf-8")
        digest = checksum(script_text)

        if path.name in done:
            recorded = done[path.name]
            if recorded is not None and recorded != digest:
                raise MigrationError(
                    f"{path.name} has changed since it was applied"
                    f" (recorded {recorded}, now {digest}). An applied"
                    " migration is skipped by name, so this edit will reach a"
                    " freshly built database and never reach this one. Add a"
                    " new migration for the change instead, or -- if the edit"
                    " is genuinely cosmetic -- update the recorded checksum"
                    " by hand.")
            continue

        script = (
            "BEGIN;\n"
            + script_text
            + "\nINSERT INTO schema_migrations (name, applied_at, checksum)"
            " VALUES (" + _sql_literal(path.name) + ", " + _sql_literal(now)
            + ", " + _sql_literal(digest) + ");\n"
            "COMMIT;\n")
        try:
            con.executescript(script)
        except Exception:
            con.rollback()
            raise
        applied.append(path.name)
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

    Called before migrate(), so it also handles a database still on the
    pre-002 schema -- the original hand-built one is exactly that, with no
    fingerprint column at all -- and refuses without having altered it.
    """
    columns = {r["name"] for r in con.execute("PRAGMA table_info(transactions)")}
    if not columns:
        return                       # no transactions table yet: fresh
    if {"origin", "fingerprint"} <= columns:
        stale = con.execute(
            "SELECT COUNT(*) FROM transactions"
            " WHERE origin = 'import' AND fingerprint = ''").fetchone()[0]
    else:
        # Pre-002: no row can carry a fingerprint, and `origin` did not exist
        # either, so every row present came from an import by construction.
        stale = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
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


def backfill_counterparty(
    con: sqlite3.Connection,
    counterparty: Callable[[str], str | None],
) -> int:
    """Fill counterparty on rows that have none. Returns rows changed.

    Wiring the extractor into the insert path only recovers the column for
    rows inserted from then on -- a database imported before the wiring
    existed keeps NULL for all 181 of its rows, and re-importing skips them
    as already present. This is safe to repair rather than refuse (unlike
    identity, cf. require_fingerprinted_imports): the value is derived purely
    from the row's own immutable description, nothing depends on it, and a
    non-NULL value is never overwritten, so a hand correction survives.
    """
    changed = 0
    rows = con.execute(
        "SELECT id, description FROM transactions"
        " WHERE counterparty IS NULL").fetchall()
    for row in rows:
        name = counterparty(row["description"])
        if name is None:
            continue
        con.execute("UPDATE transactions SET counterparty = ? WHERE id = ?",
                    (name, row["id"]))
        changed += 1
    con.commit()
    return changed


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


# --- reads and writes the HTTP API needs -----------------------------------
#
# The CLI only ever imported and counted. An API also has to list, filter,
# enter one row by hand, and correct one -- and each of those is a query with
# a sharp edge that belongs next to the schema rather than inside a route.


def list_transactions(
    con: sqlite3.Connection,
    start: str | None = None,
    end: str | None = None,
    needs_review: bool | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Transactions in date order, newest first, with their category names.

    Ordered by date then id descending: date alone is not a total order --
    every row imported from one statement day shares it -- so paging over it
    would repeat and drop rows between calls.
    """
    where = ["1 = 1"]
    params: list[object] = []
    if start is not None:
        where.append("t.date >= ?")
        params.append(start)
    if end is not None:
        where.append("t.date <= ?")
        params.append(end)
    if needs_review is not None:
        where.append("t.needs_review = ?")
        params.append(1 if needs_review else 0)

    params.extend([limit, offset])
    return list(con.execute(
        "SELECT t.*, c.name AS category, c.kind AS category_kind,"
        "       a.name AS account,"
        "       COALESCE(t.budget_override, c.budget_treatment) AS treatment"
        " FROM transactions t"
        " JOIN accounts a ON a.id = t.account_id"
        " LEFT JOIN categories c ON c.id = t.category_id"
        f" WHERE {' AND '.join(where)}"
        " ORDER BY t.date DESC, t.id DESC"
        " LIMIT ? OFFSET ?", params))


def get_transaction(con: sqlite3.Connection,
                    transaction_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT t.*, c.name AS category, c.kind AS category_kind,"
        "       a.name AS account,"
        "       COALESCE(t.budget_override, c.budget_treatment) AS treatment"
        " FROM transactions t"
        " JOIN accounts a ON a.id = t.account_id"
        " LEFT JOIN categories c ON c.id = t.category_id"
        " WHERE t.id = ?", (transaction_id,)).fetchone()


def insert_manual(
    con: sqlite3.Connection,
    date: str,
    description: str,
    amount: float,
    account_id: int,
    category: str,
    needs_review: bool = False,
    counterparty: str | None = None,
    note: str | None = None,
) -> int:
    """Insert a hand-entered transaction. Returns its id.

    origin = 'manual' and the fingerprint is left empty on purpose. A manual
    row has no source document to be identified against, so it must not carry
    a content fingerprint: 003's unique index covers `fingerprint <> ''`, and
    a manual row that happened to match an imported one would otherwise
    collide with it. `require_fingerprinted_imports` skips manual rows for the
    same reason.
    """
    kind = con.execute("SELECT id, kind FROM categories WHERE name = ?",
                       (category,)).fetchone()
    if kind is None:
        raise LookupError(f"unknown category: {category}")
    batch = _manual_batch(con)
    return con.execute(
        "INSERT INTO transactions"
        " (date, account_id, description, amount, category_id, is_transfer,"
        "  needs_review, batch_id, source_row, fingerprint, occurrence,"
        "  counterparty, note, origin)"
        " VALUES (?,?,?,?,?,?,?,?,0,'',1,?,?,'manual')",
        (date, account_id, description, amount, kind["id"],
         1 if kind["kind"] == "transfer" else 0,
         1 if needs_review else 0, batch, counterparty, note)).lastrowid


def _manual_batch(con: sqlite3.Connection) -> int:
    """One reusable batch row for hand entry.

    batch_id is NOT NULL and references import_batches, so a manual row still
    needs one. A batch per entry would bury real imports under thousands of
    one-row batches, so manual entries share a single sentinel batch.
    """
    row = con.execute(
        "SELECT id FROM import_batches WHERE source_file = 'manual entry'"
    ).fetchone()
    if row is not None:
        return row["id"]
    return con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('manual entry', 0, ?)",
        (datetime.datetime.now().isoformat(timespec="seconds"),)).lastrowid


def update_transaction(
    con: sqlite3.Connection,
    transaction_id: int,
    category: str | None = None,
    budget_override: str | None = None,
    clear_override: bool = False,
    note: str | None = None,
) -> sqlite3.Row:
    """Apply a correction to one row. Returns the row as it now stands.

    Recategorising clears needs_review: the flag means "this category is a
    guess", and a person choosing one has answered that. `is_transfer` is
    rewritten from the new category's kind, since it is derived from the
    category and would otherwise keep the old category's answer -- and that
    flag is what keeps transfers out of the spending figures.
    """
    row = con.execute("SELECT id FROM transactions WHERE id = ?",
                      (transaction_id,)).fetchone()
    if row is None:
        raise LookupError(f"no transaction {transaction_id}")

    if category is not None:
        target = con.execute(
            "SELECT id, kind FROM categories WHERE name = ?",
            (category,)).fetchone()
        if target is None:
            raise LookupError(f"unknown category: {category}")
        con.execute(
            "UPDATE transactions SET category_id = ?, is_transfer = ?,"
            " needs_review = 0 WHERE id = ?",
            (target["id"], 1 if target["kind"] == "transfer" else 0,
             transaction_id))

    if clear_override:
        con.execute(
            "UPDATE transactions SET budget_override = NULL WHERE id = ?",
            (transaction_id,))
    elif budget_override is not None:
        con.execute(
            "UPDATE transactions SET budget_override = ? WHERE id = ?",
            (budget_override, transaction_id))

    if note is not None:
        con.execute("UPDATE transactions SET note = ? WHERE id = ?",
                    (note, transaction_id))

    con.commit()
    return get_transaction(con, transaction_id)


def classify_rows(
    con: sqlite3.Connection,
    rows: Iterable[RawRow],
    account_id: int,
    categoriser: Callable[[str], "object"],
) -> list[dict]:
    """Say what importing these rows would do, without writing anything.

    The spec requires a preview before a statement upload is committed: "a
    silent half-duplicating import is painful to unpick". This runs the same
    identity computation as `upsert_transactions` and reports the verdict per
    row -- `new` or `existing` -- so the preview cannot disagree with what the
    commit then does.
    """
    out: list[dict] = []
    for row, fingerprint, occurrence in with_identity(
            list(rows), str(account_id)):
        exists = con.execute(
            "SELECT 1 FROM transactions"
            " WHERE account_id = ? AND fingerprint = ? AND occurrence = ?"
            "   AND is_derived = 0",
            (account_id, fingerprint, occurrence)).fetchone() is not None
        verdict = categoriser(row.description)
        out.append({
            "date": row.date,
            "description": row.description,
            "amount": row.amount,
            "category": verdict.category,
            "needs_review": bool(verdict.needs_review),
            "status": "existing" if exists else "new",
        })
    return out


def account_id_for(con: sqlite3.Connection, name: str) -> int:
    row = con.execute("SELECT id FROM accounts WHERE name = ?",
                      (name,)).fetchone()
    if row is None:
        raise LookupError(f"unknown account: {name}")
    return row["id"]


def list_categories(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT id, name, kind, budget_treatment, cash_treatment"
        " FROM categories ORDER BY kind, name"))


def set_category_treatment(con: sqlite3.Connection, name: str,
                           budget_treatment: str) -> sqlite3.Row:
    """Change one category's default budget treatment (a Settings action)."""
    changed = con.execute(
        "UPDATE categories SET budget_treatment = ? WHERE name = ?",
        (budget_treatment, name)).rowcount
    if not changed:
        raise LookupError(f"unknown category: {name}")
    con.commit()
    return con.execute(
        "SELECT id, name, kind, budget_treatment, cash_treatment"
        " FROM categories WHERE name = ?", (name,)).fetchone()
