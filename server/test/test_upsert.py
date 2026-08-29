"""Ingest identity and idempotency.

These are the invariants the spec calls the highest-value tests in the
project, so they run on a synthetic statement (see fixtures/statements.py)
rather than on the gitignored real ones -- guarded behind the real files,
every test in this module silently skipped on a fresh clone and in CI.

The invariants here are structural: nothing asserted below depends on the
real data, only on shapes the synthetic statement reproduces deliberately.
The real dataset's own numbers stay anchored in test_cli.py.
"""
from pathlib import Path

import pytest

from server.lib import categorise, store
from server.lib.ingest import dnb_xlsx
from server.test.fixtures import statements

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "db" / "migrations"

# Row counts come from the fixture spec, not from a number observed by
# running the code, so a change to the fixture cannot quietly invalidate them.
CARD_A_ROWS = len(statements.transactions(statements.CARD_A))
CARD_B_ROWS = len(statements.transactions(statements.CARD_B))


@pytest.fixture
def card_a(tmp_path):
    return statements.write_xlsx(
        tmp_path / "card_a.xlsx", statements.CARD_A, dnb_xlsx.CARD)


@pytest.fixture
def card_b(tmp_path):
    return statements.write_xlsx(
        tmp_path / "card_b.xlsx", statements.CARD_B, dnb_xlsx.CARD)


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


def test_first_import_inserts_every_row(con, card_a):
    inserted, skipped = load(con, card_a)
    assert (inserted, skipped) == (CARD_A_ROWS, 0)
    assert count(con) == CARD_A_ROWS


def test_reimporting_the_same_file_is_a_noop(con, card_a):
    load(con, card_a)
    inserted, skipped = load(con, card_a, "again")
    assert inserted == 0
    assert skipped == CARD_A_ROWS
    assert count(con) == CARD_A_ROWS


def test_repeat_same_day_purchases_are_both_retained(con, card_a):
    """Regression: keying identity on date+description+amount alone silently
    dropped one of each same-day pair -- in the real statement, two coffees
    bought separately. The fixture reproduces that shape twice over, at two
    different amounts; all four rows must survive."""
    load(con, card_a)
    counts = dict(con.execute(
        "SELECT amount, COUNT(*) FROM transactions"
        " WHERE description = 'Baker No Torg, Oslo'"
        "   AND date = '2026-06-30' GROUP BY amount"))
    assert counts[-238.0] == 2
    assert counts[-119.0] == 2


def test_non_overlapping_periods_both_load_fully(con, card_a, card_b):
    load(con, card_a)
    inserted, _ = load(con, card_b, "second")
    assert inserted == CARD_B_ROWS
    assert count(con) == CARD_A_ROWS + CARD_B_ROWS


def test_a_repeated_merchant_in_a_later_period_is_not_mistaken_for_a_duplicate(
        con, card_a, card_b):
    """The second statement reuses a merchant and an amount from the first
    (Baker No, -119.00) on a later date. Identity includes the date, so it is
    a new transaction, not a duplicate of the earlier pair."""
    load(con, card_a)
    load(con, card_b, "second")
    assert con.execute(
        "SELECT COUNT(*) FROM transactions"
        " WHERE description = 'Baker No Torg, Oslo' AND amount = -119.0"
    ).fetchone()[0] == 3          # two on 2026-06-30, one on 2026-07-22


def test_partial_reimport_inserts_only_the_new_rows(con, card_a):
    """The case most likely to regress: a re-export that overlaps the
    previous import partway through must add only the unseen rows."""
    rows = dnb_xlsx.read_statement(card_a, dnb_xlsx.CARD)
    head = CARD_A_ROWS - 5
    batch = new_batch(con)
    assert store.upsert_transactions(
        con, rows[:head], account_id=1, batch_id=batch,
        categoriser=categorise.categorise) == (head, 0)
    assert store.upsert_transactions(
        con, rows, account_id=1, batch_id=batch,
        categoriser=categorise.categorise) == (5, head)
    assert count(con) == CARD_A_ROWS


def test_a_reordered_reexport_is_still_recognised(con, card_a, tmp_path):
    """Identity is content, deliberately not sheet position: a bank that
    re-exports the same period with the rows in a different order must not
    produce a second copy of the statement."""
    load(con, card_a)
    shuffled = statements.write_xlsx(
        tmp_path / "reordered.xlsx",
        list(reversed(statements.CARD_A)), dnb_xlsx.CARD)
    inserted, skipped = load(con, shuffled, "reordered")
    assert (inserted, skipped) == (0, CARD_A_ROWS)
    assert count(con) == CARD_A_ROWS


def test_categories_are_assigned_on_insert(con, card_a):
    load(con, card_a)
    uncategorised = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
    ).fetchone()[0]
    assert uncategorised == 0


def test_stored_row_metadata_matches_the_import(con, card_a):
    """A regression in origin, batch_id, or fingerprint would otherwise pass
    the whole suite unnoticed."""
    batch = new_batch(con, "meta")
    rows = dnb_xlsx.read_statement(card_a, dnb_xlsx.CARD)
    inserted, _ = store.upsert_transactions(
        con, rows, account_id=1, batch_id=batch,
        categoriser=categorise.categorise)

    stored = con.execute(
        "SELECT origin, batch_id, fingerprint FROM transactions").fetchall()
    assert len(stored) == inserted == CARD_A_ROWS
    assert all(r["origin"] == "import" for r in stored)
    assert all(r["batch_id"] == batch for r in stored)
    assert all(r["fingerprint"] != "" for r in stored)


def test_counterparty_is_extracted_and_stored(con, card_a):
    """The legacy script populated counterparty for 48 of the 181 rows; the
    rebuilt database had 0, because extract_counterparty was never wired to
    the insert path and was dead code."""
    load(con, card_a)
    stored = dict(con.execute(
        "SELECT description, counterparty FROM transactions"
        " WHERE counterparty IS NOT NULL"))
    assert stored["Vipps*Aslak Fjellheim, Oslo"] == "Aslak Fjellheim"
    assert stored["Vipps*VY App, Oslo"] == "VY App"
    # A plain merchant line has no counterparty to extract.
    assert con.execute(
        "SELECT counterparty FROM transactions WHERE description = 'Innbetaling'"
    ).fetchone()[0] is None


def test_counterparty_from_a_memo_bearing_line_also_captures_the_memo(
        con, card_a):
    """Current behaviour, pinned rather than endorsed: on the `Overføring
    <account> <Name> <Memo>Tpp:` form the trailing-name pattern runs on past
    the name and takes the memo token with it. Nothing reads counterparty
    yet, so this is latent; the test is here so tightening the pattern is a
    deliberate change with a visible diff rather than a silent one."""
    load(con, card_a)
    assert con.execute(
        "SELECT counterparty FROM transactions WHERE description ="
        " 'Overføring  4790000001 Aslak Fjellheim LadingTpp: Vipps'"
    ).fetchone()[0] == "Aslak Fjellheim LadingTpp"


def test_counterparty_is_left_null_when_no_extractor_is_given(con, card_a):
    """store is persistence: the extraction is injected, not imported, so
    omitting it must simply leave the column NULL rather than fail."""
    rows = dnb_xlsx.read_statement(card_a, dnb_xlsx.CARD)
    store.upsert_transactions(
        con, rows, account_id=1, batch_id=new_batch(con, "bare"),
        categoriser=categorise.categorise)
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == 0


def test_counterparty_is_backfilled_on_rows_that_predate_the_wiring(
        con, card_a):
    """A database imported before the extractor was wired in keeps NULL for
    every row, and re-importing skips those rows as already present -- so the
    column needs repairing, not re-inserting."""
    load(con, card_a)
    expected = con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0]
    assert expected > 0
    con.execute("UPDATE transactions SET counterparty = NULL")
    con.commit()

    changed = store.backfill_counterparty(
        con, categorise.extract_counterparty)
    assert changed == expected
    assert con.execute(
        "SELECT counterparty FROM transactions"
        " WHERE description = 'Vipps*Aslak Fjellheim, Oslo'"
    ).fetchone()[0] == "Aslak Fjellheim"

    # Idempotent: a second pass finds nothing left to fill.
    assert store.backfill_counterparty(
        con, categorise.extract_counterparty) == 0


def test_backfill_never_overwrites_an_existing_counterparty(con, card_a):
    """A hand correction must survive, so only NULLs are filled."""
    load(con, card_a)
    con.execute(
        "UPDATE transactions SET counterparty = 'Corrected By Hand'"
        " WHERE description = 'Vipps*Aslak Fjellheim, Oslo'")
    con.commit()
    store.backfill_counterparty(con, categorise.extract_counterparty)
    assert con.execute(
        "SELECT counterparty FROM transactions"
        " WHERE description = 'Vipps*Aslak Fjellheim, Oslo'"
    ).fetchone()[0] == "Corrected By Hand"


def test_is_transfer_is_set_from_the_category_kind(con, card_a):
    """`r["is_transfer"] in (0, 1)` is a tautology -- the CHECK constraint
    already guarantees it, so hardcoding is_transfer = 0 in the writer passed
    the whole suite. That flag is what keeps card settlements out of
    _variable_spent, so it is asserted against actual categories here.
    """
    expected_transfers = sum(
        1 for line in statements.transactions(statements.CARD_A)
        if line.description == "Innbetaling")

    load(con, card_a)
    by_kind = dict(con.execute(
        "SELECT c.kind, SUM(t.is_transfer) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id GROUP BY c.kind"))
    counts = dict(con.execute(
        "SELECT c.kind, COUNT(*) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id GROUP BY c.kind"))

    # The `Innbetaling` card repayments are the only transfers in this
    # statement, and every one of them must be flagged.
    assert counts["transfer"] == by_kind["transfer"] == expected_transfers
    assert by_kind["expense"] == 0          # merchants are never transfers
    assert con.execute(
        "SELECT COUNT(*) FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE c.name = 'Credit card payment'"
        "   AND t.is_transfer = 1").fetchone()[0] == expected_transfers


def test_needs_review_is_set_from_the_verdict(con, card_a):
    """needs_review is the entire review queue, yet hardcoding it to 0 in the
    writer passed the whole suite. The memo-less Vipps rows are exactly the
    rows categorise flags."""
    rows = dnb_xlsx.read_statement(card_a, dnb_xlsx.CARD)
    expected = {r.description for r in rows
                if categorise.categorise(r.description).needs_review}
    assert expected                          # the fixture must exercise this

    load(con, card_a)
    flagged = {r["description"] for r in con.execute(
        "SELECT description FROM transactions WHERE needs_review = 1")}
    assert flagged == expected
    assert con.execute(
        "SELECT COUNT(*) FROM transactions WHERE needs_review = 0"
    ).fetchone()[0] == CARD_A_ROWS - len(expected)


def test_an_identical_row_on_a_second_account_is_not_skipped(con, card_a):
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
    rows = dnb_xlsx.read_statement(card_a, dnb_xlsx.CARD)

    assert store.upsert_transactions(
        con, rows, account_id=1, batch_id=new_batch(con, "a"),
        categoriser=categorise.categorise) == (CARD_A_ROWS, 0)
    # Same rows, same fingerprint inputs except the account key.
    assert store.upsert_transactions(
        con, rows, account_id=second, batch_id=new_batch(con, "b"),
        categoriser=categorise.categorise) == (CARD_A_ROWS, 0)
    assert count(con) == CARD_A_ROWS * 2

    # ... and each account is still individually idempotent.
    assert store.upsert_transactions(
        con, rows, account_id=second, batch_id=new_batch(con, "c"),
        categoriser=categorise.categorise) == (0, CARD_A_ROWS)
    assert count(con) == CARD_A_ROWS * 2


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
