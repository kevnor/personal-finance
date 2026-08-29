"""The two account-holder corrections, applied from code rather than by hand.

They existed only in db/README's prose and in a heredoc that ran once
against a gitignored database. A fresh clone plus `import` therefore
produced a dataset missing both -- and still passed the 181-row /
14 084,24 reconciliation, because neither correction changes the net.
"""
from pathlib import Path

import pytest

from server import cli, corrections
from server.lib import rules, store
from server.test.fixtures import statements

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
MIGRATIONS = ROOT / "db" / "migrations"

needs_statements = pytest.mark.skipif(
    not (INPUT / "Kontoutskrift.xlsx").exists(),
    reason="statements not present")

BOK_INGVILD = ("Overføring  9260000000 Ingvild Kvamme Berg BokTpp:"
              " Vipps Mobilepay AS")
BOK_TORKEL = "Overføring  92800000000 Torkel Aalborg BokTpp: Vipps"
PHONE = "Mol*Hoome AS, 4799000000"


@pytest.fixture
def con(tmp_path):
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    return store.connect(db)


def category_of(con, description):
    return con.execute(
        "SELECT c.name FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE t.description = ?",
        (description,)).fetchone()["name"]


@needs_statements
def test_import_moves_both_bok_rows_to_gifts(con):
    """A memo says what was bought, not why: the book was a present for the
    account holder's mother, split three ways."""
    assert category_of(con, BOK_INGVILD) == "Gifts"
    assert category_of(con, BOK_TORKEL) == "Gifts"


@needs_statements
def test_books_is_empty_and_gifts_nets_to_the_account_holders_own_share(con):
    """db/README decision 7: Gifts nets to 56,00 (166 out, two 55,00 shares
    back) and Books is left empty."""
    assert con.execute(
        "SELECT COUNT(*) FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE c.name = 'Books'").fetchone()[0] == 0
    assert con.execute(
        "SELECT ROUND(SUM(-t.amount), 2) FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE c.name = 'Gifts'").fetchone()[0] == 56.0


@needs_statements
def test_import_records_the_phone_as_a_debt_owed_by_the_employer(con):
    owed = rules.outstanding(con)
    assert len(owed) == 1
    assert owed[0]["expected_from"] == "Nordvest Teknikk AS"
    assert owed[0]["expected_amount"] == 13990.0
    assert owed[0]["description"] == PHONE
    assert con.execute(
        "SELECT budget_override FROM transactions WHERE description = ?",
        (PHONE,)).fetchone()[0] == "reimbursable"


@needs_statements
def test_the_phone_keeps_its_category_for_reporting(con):
    """Marking a debt says nothing about whether the category is right, so
    Home & furniture stays -- that is what makes it a reimbursement rather
    than a recategorisation."""
    assert category_of(con, PHONE) == "Home & furniture"


@needs_statements
def test_applying_twice_is_a_no_op(con):
    first = corrections.apply(con)
    assert first == {"applied": 0, "already": 3, "missing": 0}
    second = corrections.apply(con)
    assert second == first
    assert len(rules.outstanding(con)) == 1
    assert category_of(con, BOK_INGVILD) == "Gifts"


@needs_statements
def test_a_fresh_build_reports_the_corrections_it_applied(tmp_path):
    result = cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    assert result["corrections"] == {"applied": 3, "already": 0, "missing": 0}
    # ... and a second import finds nothing left to do.
    again = cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    assert again["corrections"] == {"applied": 0, "already": 3, "missing": 0}


@needs_statements
def test_the_corrections_change_neither_the_row_count_nor_the_net(tmp_path):
    """Which is exactly why their absence went unnoticed: the reconciliation
    invariant cannot see them."""
    result = cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    assert (result["count"], result["net"]) == (181, 14084.24)


@needs_statements
def test_missing_rows_are_counted_rather_than_raised(tmp_path):
    """Corrections are dataset-specific; a partial import is a legitimate
    state, but a silent no-op must still be visible in the output."""
    partial = tmp_path / "input"
    partial.mkdir()
    (partial / "transaksjonsliste.xlsx").write_bytes(
        (INPUT / "transaksjonsliste.xlsx").read_bytes())
    result = cli.build(tmp_path / "t.db", partial, MIGRATIONS)
    assert result["corrections"]["missing"] == 2   # the two Vipps Bok rows
    assert result["corrections"]["applied"] == 1   # the phone is on this card


@needs_statements
def test_an_ambiguous_correction_key_is_refused(con):
    """Content-keyed corrections must name exactly one row. A duplicate would
    otherwise silently recategorise whichever row SQLite returned first."""
    row = con.execute(
        "SELECT * FROM transactions WHERE description = ?",
        (BOK_INGVILD,)).fetchone()
    con.execute(
        "INSERT INTO transactions (date, account_id, description, amount,"
        " category_id, batch_id, source_row, fingerprint, occurrence)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (row["date"], row["account_id"], row["description"], row["amount"],
         row["category_id"], row["batch_id"], 9999, "dupfp", 1))
    con.commit()
    with pytest.raises(LookupError):
        corrections.apply(con)


# -- the correction mechanics, independent of the two real corrections ------
#
# `apply` reads module-level lists, so these drive it with corrections of
# their own against a synthetic dataset. Without them the module that runs on
# every `import` had no coverage at all on a fresh clone.

# This merchant appears on three different dates across the fixture's three
# statements, which is the point: a content-keyed correction must reach the
# one row it names and leave the others alone.
GROCERY = corrections.Row("2026-07-02", "Rema Lorenveien, Oslo", -189.90)


def category_of_row(con, row):
    """Look the row up by the same content key the correction uses."""
    return con.execute(
        "SELECT c.name FROM transactions t JOIN categories c"
        " ON c.id = t.category_id"
        " WHERE t.date = ? AND t.description = ? AND t.amount = ?",
        (row.date, row.description, row.amount)).fetchone()["name"]


def override_of_row(con, row):
    return con.execute(
        "SELECT budget_override FROM transactions"
        " WHERE date = ? AND description = ? AND amount = ?",
        (row.date, row.description, row.amount)).fetchone()[0]


@pytest.fixture
def synthetic(tmp_path):
    inp = statements.write_input_dir(tmp_path / "input")
    db = tmp_path / "s.db"
    cli.build(db, inp, MIGRATIONS)
    return store.connect(db)


@pytest.fixture
def only(monkeypatch):
    """Replace the correction lists for the duration of one test."""
    def use(recategorisations=(), reimbursements=()):
        monkeypatch.setattr(corrections, "RECATEGORISATIONS",
                            list(recategorisations))
        monkeypatch.setattr(corrections, "REIMBURSEMENTS",
                            list(reimbursements))
    return use


def test_a_recategorisation_applies_once_and_then_reports_already(
        synthetic, only):
    only(recategorisations=[(GROCERY, "Gifts")])

    assert corrections.apply(synthetic) == {
        "applied": 1, "already": 0, "missing": 0}
    assert category_of_row(synthetic, GROCERY) == "Gifts"
    assert corrections.apply(synthetic) == {
        "applied": 0, "already": 1, "missing": 0}


def test_a_recategorisation_touches_only_the_row_it_names(synthetic, only):
    """The same merchant appears on other dates and for other amounts. A
    correction is about one payment, so those must keep their category."""
    only(recategorisations=[(GROCERY, "Gifts")])
    corrections.apply(synthetic)

    others = [corrections.Row("2026-07-07", "Rema Lorenveien, Oslo", -402.10),
              corrections.Row("2026-07-21", "Rema Lorenveien, Oslo", -212.40)]
    assert all(category_of_row(synthetic, r) == "Groceries" for r in others)


def test_a_correction_naming_an_absent_row_is_counted_not_raised(
        synthetic, only):
    """Corrections are dataset-specific; a partial import is a legitimate
    state, but a silent no-op must still be visible in the output."""
    only(recategorisations=[
        (corrections.Row("2026-07-02", "Nowhere AS", -1.0), "Gifts")])
    assert corrections.apply(synthetic) == {
        "applied": 0, "already": 0, "missing": 1}


def test_a_reimbursement_marks_the_row_and_records_the_debt(synthetic, only):
    only(reimbursements=[(GROCERY, "Acme AS", "note")])

    assert corrections.apply(synthetic) == {
        "applied": 1, "already": 0, "missing": 0}
    owed = rules.outstanding(synthetic)
    assert len(owed) == 1
    assert owed[0]["expected_from"] == "Acme AS"
    assert owed[0]["expected_amount"] == 189.90
    # The category is untouched: marking a debt says nothing about whether
    # the category is right.
    assert category_of_row(synthetic, GROCERY) == "Groceries"
    assert override_of_row(synthetic, GROCERY) == "reimbursable"

    # Re-applying neither duplicates the debt nor doubles the amount.
    assert corrections.apply(synthetic) == {
        "applied": 0, "already": 1, "missing": 0}
    assert len(rules.outstanding(synthetic)) == 1


def test_an_ambiguous_correction_key_is_refused_synthetic(synthetic, only):
    """Content-keyed corrections must name exactly one row. The fixture's two
    same-day, same-amount cafe purchases are genuinely distinct transactions,
    so a correction keyed on their shared content cannot say which it means.
    """
    only(recategorisations=[
        (corrections.Row("2026-06-30", "Baker No Torg, Oslo", -238.0),
         "Gifts")])
    with pytest.raises(LookupError):
        corrections.apply(synthetic)


def test_an_unknown_target_category_is_refused(synthetic, only):
    only(recategorisations=[(GROCERY, "No Such Category")])
    with pytest.raises(LookupError):
        corrections.apply(synthetic)
