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
        batch_id=batch, categoriser=categorise.categorise,
        counterparty=categorise.extract_counterparty)


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
    """A regression in origin, batch_id, or fingerprint would otherwise pass
    the whole suite unnoticed."""
    batch = new_batch(con, "meta")
    rows = dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)
    inserted, _ = store.upsert_transactions(
        con, rows, account_id=1, batch_id=batch,
        categoriser=categorise.categorise)

    stored = con.execute(
        "SELECT origin, batch_id, fingerprint FROM transactions").fetchall()
    assert len(stored) == inserted == 43
    assert all(r["origin"] == "import" for r in stored)
    assert all(r["batch_id"] == batch for r in stored)
    assert all(r["fingerprint"] != "" for r in stored)


def test_counterparty_is_extracted_and_stored(con):
    """The legacy script populated counterparty for 48 of the 181 rows; the
    rebuilt database had 0, because extract_counterparty was never wired to
    the insert path and was dead code."""
    load(con, CARD_1)
    stored = dict(con.execute(
        "SELECT description, counterparty FROM transactions"
        " WHERE counterparty IS NOT NULL"))
    assert stored["Vipps*Bjarte Lunde Sk, Oslo"] == "Bjarte Lunde Sk"
    assert stored["Vipps*VY App, Oslo"] == "VY App"
    # A plain merchant line has no counterparty to extract.
    assert con.execute(
        "SELECT counterparty FROM transactions WHERE description = 'Innbetaling'"
    ).fetchone()[0] is None


def test_counterparty_is_left_null_when_no_extractor_is_given(con):
    """store is persistence: the extraction is injected, not imported, so
    omitting it must simply leave the column NULL rather than fail."""
    rows = dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)
    store.upsert_transactions(
        con, rows, account_id=1, batch_id=new_batch(con, "bare"),
        categoriser=categorise.categorise)
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == 0


def test_counterparty_is_backfilled_on_rows_that_predate_the_wiring(con):
    """A database imported before the extractor was wired in keeps NULL for
    every row, and re-importing skips those rows as already present -- so the
    column needs repairing, not re-inserting."""
    load(con, CARD_1)
    con.execute("UPDATE transactions SET counterparty = NULL")
    con.commit()

    changed = store.backfill_counterparty(
        con, categorise.extract_counterparty)
    assert changed == 12
    assert con.execute(
        "SELECT counterparty FROM transactions"
        " WHERE description = 'Vipps*Bjarte Lunde Sk, Oslo'"
    ).fetchone()[0] == "Bjarte Lunde Sk"

    # Idempotent: a second pass finds nothing left to fill.
    assert store.backfill_counterparty(
        con, categorise.extract_counterparty) == 0


def test_backfill_never_overwrites_an_existing_counterparty(con):
    """A hand correction must survive, so only NULLs are filled."""
    load(con, CARD_1)
    con.execute(
        "UPDATE transactions SET counterparty = 'Corrected By Hand'"
        " WHERE description = 'Vipps*Bjarte Lunde Sk, Oslo'")
    con.commit()
    store.backfill_counterparty(con, categorise.extract_counterparty)
    assert con.execute(
        "SELECT counterparty FROM transactions"
        " WHERE description = 'Vipps*Bjarte Lunde Sk, Oslo'"
    ).fetchone()[0] == "Corrected By Hand"


def test_is_transfer_is_set_from_the_category_kind(con):
    """`r["is_transfer"] in (0, 1)` is a tautology -- the CHECK constraint
    already guarantees it, so hardcoding is_transfer = 0 in the writer passed
    the whole suite. That flag is what keeps ~26 912 kr of card settlements
    out of _variable_spent, so it is asserted against actual categories here.
    """
    load(con, CARD_1)
    by_kind = dict(con.execute(
        "SELECT c.kind, SUM(t.is_transfer) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id GROUP BY c.kind"))
    counts = dict(con.execute(
        "SELECT c.kind, COUNT(*) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id GROUP BY c.kind"))

    # The six `Innbetaling` card repayments are the only transfers in this
    # statement, and every one of them must be flagged.
    assert counts["transfer"] == by_kind["transfer"] == 6
    assert by_kind["expense"] == 0          # merchants are never transfers
    assert con.execute(
        "SELECT COUNT(*) FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE c.name = 'Credit card payment'"
        "   AND t.is_transfer = 1").fetchone()[0] == 6


def test_needs_review_is_set_from_the_verdict(con):
    """needs_review is the entire review queue, yet hardcoding it to 0 in the
    writer passed the whole suite. This statement's six memo-less Vipps rows
    are exactly the rows categorise flags."""
    rows = dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)
    expected = {r.description for r in rows
                if categorise.categorise(r.description).needs_review}
    assert len(expected) == 6

    load(con, CARD_1)
    flagged = {r["description"] for r in con.execute(
        "SELECT description FROM transactions WHERE needs_review = 1")}
    assert flagged == expected
    assert con.execute(
        "SELECT COUNT(*) FROM transactions WHERE needs_review = 0"
    ).fetchone()[0] == 37


def test_an_identical_row_on_a_second_account_is_not_skipped(con):
    """Identity is scoped by account, so the same purchase appearing on two
    accounts is two transactions. Dropping account_id from the existence
    check passed the whole suite: nothing imported the same rows under two
    account ids, and the fingerprint already hashes account_key, which masks
    the omission until two accounts genuinely share one.
    """
    con.execute("INSERT INTO accounts (name, kind) VALUES ('Andre','credit_card')")
    con.commit()
    second = con.execute(
        "SELECT id FROM accounts WHERE name = 'Andre'").fetchone()["id"]
    rows = dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)

    assert store.upsert_transactions(
        con, rows, account_id=1, batch_id=new_batch(con, "a"),
        categoriser=categorise.categorise) == (43, 0)
    # Same rows, same fingerprint inputs except the account key.
    assert store.upsert_transactions(
        con, rows, account_id=second, batch_id=new_batch(con, "b"),
        categoriser=categorise.categorise) == (43, 0)
    assert count(con) == 86

    # ... and each account is still individually idempotent.
    assert store.upsert_transactions(
        con, rows, account_id=second, batch_id=new_batch(con, "c"),
        categoriser=categorise.categorise) == (0, 43)
    assert count(con) == 86


def test_derived_identity_is_also_scoped_by_account(con):
    """insert_derived_rows shares upsert's identity scheme and has no unique
    index behind it (003 excludes is_derived = 1), so its existence check is
    the only thing standing between a repeat run and a duplicated split."""
    con.execute("INSERT INTO accounts (name, kind) VALUES ('Andre','credit_card')")
    con.commit()
    second = con.execute(
        "SELECT id FROM accounts WHERE name = 'Andre'").fetchone()["id"]

    row = dnb_xlsx.RawRow("2026-07-20", "Lån 12345678901 Avdrag", -100.0, 7)
    parts = [type("P", (), {"description": "part", "amount": -100.0,
                            "category": "Groceries"})()]

    def splitter(_description, _amount):
        return parts

    for account in (1, second):
        assert store.insert_derived_rows(
            con, [row], account_id=account, batch_id=new_batch(con, "d"),
            splitter=splitter) == (1, 0, 1)
    assert count(con) == 2

    # Repeating either account is still a no-op.
    assert store.insert_derived_rows(
        con, [row], account_id=second, batch_id=new_batch(con, "e"),
        splitter=splitter) == (0, 1, 0)
    assert count(con) == 2
