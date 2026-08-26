from pathlib import Path

import pytest

from server.lib import categorise, store
from server.lib.ingest import dnb_xlsx

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "db" / "migrations"
CARD_1 = ROOT / "input" / "transaksjonsliste(1).xlsx"
CARD_2 = ROOT / "input" / "transaksjonsliste.xlsx"

pytestmark = pytest.mark.skipif(
    not CARD_1.exists(), reason="statements not present")


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.migrate(c, MIGRATIONS)
    store.seed_reference_data(
        c, categorise.CATEGORIES, categorise.TREATMENTS,
        [("Kredittkort", "credit_card")])
    return c


def new_batch(con, label="f"):
    return con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES (?, 0, '2026-08-22')", (label,)).lastrowid


def load(con, path, label="f"):
    batch = new_batch(con, label)
    rows = dnb_xlsx.read_statement(path, dnb_xlsx.CARD)
    return store.upsert_transactions(
        con, rows, account_id=1,
        batch_id=batch, categoriser=categorise.categorise)


def count(con):
    return con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]


def test_first_import_inserts_every_row(con):
    inserted, skipped = load(con, CARD_1)
    assert (inserted, skipped) == (43, 0)
    assert count(con) == 43


def test_reimporting_the_same_file_is_a_noop(con):
    load(con, CARD_1)
    inserted, skipped = load(con, CARD_1, "again")
    assert inserted == 0
    assert skipped == 43
    assert count(con) == 43


def test_repeat_same_day_purchases_are_both_retained(con):
    """Regression: keying identity on date+description+amount alone silently
    dropped one 238 and one 119 — two coffees bought separately on
    2026-06-30. Both pairs must survive."""
    load(con, CARD_1)
    counts = dict(con.execute(
        "SELECT amount, COUNT(*) FROM transactions"
        " WHERE upper(description) LIKE 'PROUD MARY OSLO, OSLO%'"
        "   AND date = '2026-06-30' GROUP BY amount"))
    assert counts[-238.0] == 2
    assert counts[-119.0] == 2


def test_non_overlapping_periods_both_load_fully(con):
    load(con, CARD_1)
    inserted, _ = load(con, CARD_2, "second")
    assert inserted == 13
    assert count(con) == 56


def test_partial_reimport_inserts_only_the_new_rows(con):
    """The case most likely to regress: a re-export that overlaps the
    previous import partway through must add only the unseen rows."""
    rows = dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)
    batch = new_batch(con)
    assert store.upsert_transactions(
        con, rows[:38], account_id=1, batch_id=batch,
        categoriser=categorise.categorise) == (38, 0)
    assert store.upsert_transactions(
        con, rows, account_id=1, batch_id=batch,
        categoriser=categorise.categorise) == (5, 38)
    assert count(con) == 43


def test_categories_are_assigned_on_insert(con):
    load(con, CARD_1)
    uncategorised = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
    ).fetchone()[0]
    assert uncategorised == 0


def test_stored_row_metadata_matches_the_import(con):
    """A regression in origin, batch_id, is_transfer, or fingerprint would
    otherwise pass the whole suite unnoticed."""
    batch = new_batch(con, "meta")
    rows = dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)
    inserted, _ = store.upsert_transactions(
        con, rows, account_id=1, batch_id=batch,
        categoriser=categorise.categorise)

    stored = con.execute(
        "SELECT origin, batch_id, is_transfer, fingerprint"
        " FROM transactions").fetchall()
    assert len(stored) == inserted == 43
    assert all(r["origin"] == "import" for r in stored)
    assert all(r["batch_id"] == batch for r in stored)
    assert all(r["is_transfer"] in (0, 1) for r in stored)
    assert all(r["fingerprint"] != "" for r in stored)
