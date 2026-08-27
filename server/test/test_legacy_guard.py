"""The guard against importing into a pre-fingerprint database.

Migration 002 backfills fingerprint = '' and 003's partial unique index
deliberately excludes those rows, so nothing -- not the application check,
not the database -- recognises a legacy row. Importing the same statements
over one produced 362 rows and net 28168.48 on a copy of the original
hand-built database, and did so stably across repeated runs.
"""
from pathlib import Path

import pytest

from server import cli
from server.lib import store

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
MIGRATIONS = ROOT / "db" / "migrations"


def legacy_db(tmp_path, rows=3, origin=None, migrated=True):
    """A database shaped like the pre-fingerprint one.

    Built by applying 001 alone and inserting rows. With `migrated` it then
    applies the rest, which is how the real legacy database would reach the
    fingerprint = '' state; without it, the database stays on the pre-002
    schema the original hand-built one is actually on -- no fingerprint or
    origin column at all.
    """
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "001_baseline.sql").write_text(
        (MIGRATIONS / "001_baseline.sql").read_text(encoding="utf-8"),
        encoding="utf-8")

    con = store.connect(tmp_path / "legacy.db")
    store.migrate(con, baseline)
    con.execute("INSERT INTO accounts (name, kind) VALUES ('Bankkonto','bank')")
    con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('Kontoutskrift.xlsx', ?, '2026-08-22')", (rows,))
    for n in range(rows):
        con.execute(
            "INSERT INTO transactions (date, account_id, description, amount,"
            " batch_id, source_row) VALUES ('2026-07-01', 1, ?, -100.0, 1, ?)",
            (f"REMA 1000 row {n}", n + 1))
    con.commit()

    if migrated:
        store.migrate(con, MIGRATIONS)  # 002 backfills fingerprint = ''
    if origin is not None:
        con.execute("UPDATE transactions SET origin = ?", (origin,))
        con.commit()
    return con


def test_guard_fires_on_unfingerprinted_import_rows(tmp_path):
    con = legacy_db(tmp_path)
    assert con.execute(
        "SELECT COUNT(*) FROM transactions WHERE fingerprint = ''"
    ).fetchone()[0] == 3

    with pytest.raises(store.LegacyDataError) as exc:
        store.require_fingerprinted_imports(con)
    message = str(exc.value)
    assert "3 imported transactions" in message
    assert "fingerprint" in message
    assert "legacy-2026-08-22.db" in message   # names the recovery path


def test_guard_ignores_manual_rows_which_legitimately_have_no_fingerprint(
        tmp_path):
    """Manual entry is the whole reason ingest became additive; those rows
    carry no fingerprint by design and must not block an import."""
    con = legacy_db(tmp_path, origin="manual")
    store.require_fingerprinted_imports(con)


def test_guard_fires_on_a_pre_002_schema_with_no_fingerprint_column(tmp_path):
    """The real hand-built database is on this schema: no fingerprint column,
    no origin column, no schema_migrations table. Every row it holds came
    from an import by construction."""
    con = legacy_db(tmp_path, migrated=False)
    columns = {r["name"] for r in con.execute("PRAGMA table_info(transactions)")}
    assert "fingerprint" not in columns

    with pytest.raises(store.LegacyDataError):
        store.require_fingerprinted_imports(con)


@pytest.mark.skipif(not (INPUT / "Kontoutskrift.xlsx").exists(),
                    reason="statements not present")
def test_import_refuses_a_legacy_database_without_altering_its_schema(tmp_path):
    """The guard runs before migrate, so a database this refuses is left
    exactly as it was found -- not silently upgraded on the way to a
    refusal."""
    con = legacy_db(tmp_path, migrated=False)
    before = {r[0] for r in con.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")}
    con.close()

    with pytest.raises(store.LegacyDataError):
        cli.build(tmp_path / "legacy.db", INPUT, MIGRATIONS)

    after = store.connect(tmp_path / "legacy.db")
    assert {r[0] for r in after.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")} == before
    assert after.execute(
        "SELECT COUNT(*) FROM transactions").fetchone()[0] == 3


def test_guard_is_silent_on_an_empty_database(tmp_path):
    con = store.connect(tmp_path / "fresh.db")
    store.migrate(con, MIGRATIONS)
    store.require_fingerprinted_imports(con)


@pytest.mark.skipif(not (INPUT / "Kontoutskrift.xlsx").exists(),
                    reason="statements not present")
def test_import_refuses_a_legacy_database_instead_of_doubling_it(tmp_path):
    con = legacy_db(tmp_path)
    con.close()
    db = tmp_path / "legacy.db"

    with pytest.raises(store.LegacyDataError):
        cli.build(db, INPUT, MIGRATIONS)

    check = store.connect(db)
    assert check.execute(
        "SELECT COUNT(*) FROM transactions").fetchone()[0] == 3


@pytest.mark.skipif(not (INPUT / "Kontoutskrift.xlsx").exists(),
                    reason="statements not present")
def test_guard_does_not_block_a_database_this_pipeline_built(tmp_path):
    """Every row the current importer writes carries a fingerprint, so a
    second import must still be the ordinary no-op."""
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    second = cli.build(db, INPUT, MIGRATIONS)
    assert second["inserted"] == 0
    assert second["count"] == 181
