"""Corrections: facts about specific payments that no rule can express.

The corrections themselves are one household's data and live in a gitignored
local file, so there is nothing dataset-specific to assert here. What is
worth asserting is the mechanism, and it runs on every import: content-keyed
lookup, idempotency, and the refusals -- an ambiguous key, an unknown
category -- that stop a correction quietly landing on the wrong row.

Everything below drives `apply` with corrections it constructs itself
against the synthetic statements, so it runs everywhere.
"""
from pathlib import Path

import pytest

from server import cli, corrections
from server.lib import local, rules, store
from server.test.fixtures import statements

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "db" / "migrations"

# This merchant appears on three different dates across the fixture's three
# statements, which is the point: a content-keyed correction must reach the
# one row it names and leave the others alone.
GROCERY = local.Correction("2026-07-02", "Rema Lorenveien, Oslo", -189.90)
OTHER_GROCERIES = [
    local.Correction("2026-07-07", "Rema Lorenveien, Oslo", -402.10),
    local.Correction("2026-07-21", "Rema Lorenveien, Oslo", -212.40),
]


@pytest.fixture
def con(tmp_path):
    inp = statements.write_input_dir(tmp_path / "input")
    db = tmp_path / "s.db"
    cli.build(db, inp, MIGRATIONS)
    return store.connect(db)


def category_of(con, row):
    return con.execute(
        "SELECT c.name FROM transactions t JOIN categories c"
        " ON c.id = t.category_id"
        " WHERE t.date = ? AND t.description = ? AND t.amount = ?",
        (row.date, row.description, row.amount)).fetchone()["name"]


def override_of(con, row):
    return con.execute(
        "SELECT budget_override FROM transactions"
        " WHERE date = ? AND description = ? AND amount = ?",
        (row.date, row.description, row.amount)).fetchone()[0]


# -- recategorisation -------------------------------------------------------

def test_a_recategorisation_applies_once_and_then_reports_already(con):
    data = local.LocalData(recategorisations=((GROCERY, "Gifts"),))

    assert corrections.apply(con, data) == {
        "applied": 1, "already": 0, "missing": 0}
    assert category_of(con, GROCERY) == "Gifts"
    assert corrections.apply(con, data) == {
        "applied": 0, "already": 1, "missing": 0}


def test_a_recategorisation_touches_only_the_row_it_names(con):
    """The same merchant appears on other dates and for other amounts. A
    correction is about one payment, so those must keep their category."""
    corrections.apply(con, local.LocalData(
        recategorisations=((GROCERY, "Gifts"),)))
    assert all(category_of(con, row) == "Groceries" for row in OTHER_GROCERIES)


def test_a_correction_naming_an_absent_row_is_counted_not_raised(con):
    """Corrections are dataset-specific; a partial import is a legitimate
    state, but a silent no-op must still be visible in the output."""
    absent = local.Correction("2026-07-02", "Nowhere AS", -1.0)
    assert corrections.apply(
        con, local.LocalData(recategorisations=((absent, "Gifts"),))
    ) == {"applied": 0, "already": 0, "missing": 1}


def test_an_ambiguous_correction_key_is_refused(con):
    """Content-keyed corrections must name exactly one row. The fixture's two
    same-day, same-amount cafe purchases are genuinely distinct transactions,
    so a correction keyed on their shared content cannot say which it means --
    and picking whichever SQLite returned first would be silently wrong."""
    ambiguous = local.Correction("2026-06-30", "Baker No Torg, Oslo", -238.0)
    with pytest.raises(LookupError):
        corrections.apply(con, local.LocalData(
            recategorisations=((ambiguous, "Gifts"),)))


def test_an_unknown_target_category_is_refused(con):
    with pytest.raises(LookupError):
        corrections.apply(con, local.LocalData(
            recategorisations=((GROCERY, "No Such Category"),)))


# -- reimbursement ----------------------------------------------------------

def test_a_reimbursement_marks_the_row_and_records_the_debt(con):
    data = local.LocalData(reimbursements=((GROCERY, "Acme AS", "note"),))

    assert corrections.apply(con, data) == {
        "applied": 1, "already": 0, "missing": 0}
    owed = rules.outstanding(con)
    assert len(owed) == 1
    assert owed[0]["expected_from"] == "Acme AS"
    assert owed[0]["expected_amount"] == 189.90
    # The category is untouched: marking a debt says nothing about whether
    # the category is right, which is what makes it a reimbursement rather
    # than a recategorisation.
    assert category_of(con, GROCERY) == "Groceries"
    assert override_of(con, GROCERY) == "reimbursable"

    # Re-applying neither duplicates the debt nor doubles the amount owed.
    assert corrections.apply(con, data) == {
        "applied": 0, "already": 1, "missing": 0}
    assert len(rules.outstanding(con)) == 1


# -- no local file ----------------------------------------------------------

def test_no_corrections_at_all_is_a_clean_no_op(con):
    """A fresh clone has no household attached to it, and that is a normal
    state rather than a broken one."""
    assert corrections.apply(con) == {"applied": 0, "already": 0, "missing": 0}
    assert corrections.apply(con, local.EMPTY) == {
        "applied": 0, "already": 0, "missing": 0}


def test_an_import_without_a_local_file_reports_no_corrections(tmp_path):
    result = cli.build(tmp_path / "t.db",
                       statements.write_input_dir(tmp_path / "input"),
                       MIGRATIONS)
    assert result["corrections"] == {"applied": 0, "already": 0, "missing": 0}


def test_an_import_applies_the_local_file_when_there_is_one(tmp_path):
    """End to end: the file beside the database is what `import` reads."""
    import json

    db = tmp_path / "data" / "t.db"
    db.parent.mkdir(parents=True)
    local.path_for(db.parent).write_text(json.dumps({
        "recategorisations": [{
            "date": GROCERY.date, "description": GROCERY.description,
            "amount": GROCERY.amount, "category": "Gifts"}],
    }), encoding="utf-8")

    result = cli.build(db, statements.write_input_dir(tmp_path / "input"),
                       MIGRATIONS)
    assert result["corrections"] == {"applied": 1, "already": 0, "missing": 0}
    assert category_of(store.connect(db), GROCERY) == "Gifts"
