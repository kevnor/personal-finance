"""Persistence: connections, migrations, and transaction writes."""
from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path


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
