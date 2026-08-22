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


def load(con, path, label="f"):
    batch = con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES (?, 0, '2026-08-22')", (label,)).lastrowid
    rows = dnb_xlsx.read_statement(path, dnb_xlsx.CARD)
    return store.upsert_transactions(
        con, rows, account_id=1, account_name="Kredittkort",
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


def test_categories_are_assigned_on_insert(con):
    load(con, CARD_1)
    uncategorised = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
    ).fetchone()[0]
    assert uncategorised == 0
