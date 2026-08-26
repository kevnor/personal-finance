from pathlib import Path

import pytest

from server.lib import categorise, rules, store

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "t.db")
    store.migrate(c, MIGRATIONS)
    store.seed_reference_data(
        c, categorise.CATEGORIES, categorise.TREATMENTS, [("K", "credit_card")])
    c.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES ('f',0,'2026-08-22')")
    c.commit()
    return c


def add(con, desc, amount, category="Uncategorised", needs_review=0):
    cid = con.execute("SELECT id FROM categories WHERE name=?",
                      (category,)).fetchone()[0]
    return con.execute(
        "INSERT INTO transactions (date, account_id, description, amount,"
        " category_id, needs_review, batch_id, source_row, fingerprint, occurrence)"
        " VALUES ('2026-07-31',1,?,?,?,?,1,2,'fp',1)",
        (desc, amount, cid, needs_review)).lastrowid


def test_teach_then_learned_map_returns_the_rule(con):
    rules.teach(con, "ecom capital", "Subscriptions")
    assert rules.learned_map(con) == {"ecom capital": "Subscriptions"}


def test_teaching_the_same_pattern_twice_updates_not_duplicates(con):
    rules.teach(con, "ecom capital", "Subscriptions")
    rules.teach(con, "ecom capital", "Entertainment")
    assert rules.learned_map(con) == {"ecom capital": "Entertainment"}
    assert con.execute("SELECT COUNT(*) FROM merchant_rules").fetchone()[0] == 1


def test_learned_rule_changes_categorisation_outcome(con):
    rules.teach(con, "ecom capital", "Subscriptions")
    verdict = categorise.categorise("Visa  100121  Ecom Capital AS",
                                    learned=rules.learned_map(con))
    assert verdict.category == "Subscriptions"


def test_learned_map_orders_longest_pattern_first(con):
    """When two taught patterns both substring-match, the more specific
    (longer) one must win deterministically -- not whatever SQLite happens
    to return first."""
    rules.teach(con, "capital", "Entertainment")
    rules.teach(con, "ecom capital", "Subscriptions")

    keys = list(rules.learned_map(con).keys())
    assert keys[0] == "ecom capital"

    verdict = categorise.categorise("Visa  100121  Ecom Capital AS",
                                    learned=rules.learned_map(con))
    assert verdict.category == "Subscriptions"


def test_mark_reimbursable_sets_override_and_records_the_debt(con):
    tid = add(con, "Mol*Hoome AS, 4799000000", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")

    row = con.execute(
        "SELECT budget_override FROM transactions WHERE id=?", (tid,)).fetchone()
    assert row["budget_override"] == "reimbursable"

    debt = con.execute("SELECT * FROM reimbursements").fetchone()
    assert debt["expected_from"] == "Nordvest Teknikk AS"
    assert debt["expected_amount"] == 13990.0
    assert debt["settled_at"] is None


def test_reimbursable_row_keeps_its_reporting_category(con):
    """Category is for reporting; the override is what leaves the budget."""
    tid = add(con, "Mol*Hoome AS", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    name = con.execute(
        "SELECT c.name FROM transactions t JOIN categories c"
        " ON c.id=t.category_id WHERE t.id=?", (tid,)).fetchone()[0]
    assert name == "Home & furniture"


def test_marking_reimbursable_twice_does_not_double_the_debt(con):
    """A retry or double-submit must not double the amount owed."""
    tid = add(con, "Mol*Hoome AS", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")

    rows = con.execute("SELECT * FROM reimbursements").fetchall()
    assert len(rows) == 1
    assert rows[0]["expected_amount"] == 13990.0

    outstanding = rules.outstanding(con)
    assert len(outstanding) == 1
    assert outstanding[0]["expected_amount"] == 13990.0


def test_marking_reimbursable_refreshes_the_existing_debt(con):
    tid = add(con, "Mol*Hoome AS", -13990.0, "Home & furniture")
    first_id = rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    second_id = rules.mark_reimbursable(con, tid, "Employer AS", note="corrected payer")

    assert second_id == first_id
    row = con.execute("SELECT * FROM reimbursements WHERE id=?", (first_id,)).fetchone()
    assert row["expected_from"] == "Employer AS"
    assert row["note"] == "corrected payer"


def test_marking_reimbursable_does_not_clear_needs_review(con):
    """Recording a debt says nothing about whether the category is right --
    needs_review is cleared by recategorising, not by mark_reimbursable."""
    tid = add(con, "Some Unknown Merchant", -13990.0, "Uncategorised", needs_review=1)
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    row = con.execute("SELECT needs_review FROM transactions WHERE id=?", (tid,)).fetchone()
    assert row["needs_review"] == 1


def test_outstanding_lists_unsettled_only(con):
    tid = add(con, "Mol*Hoome AS", -13990.0, "Home & furniture")
    rules.mark_reimbursable(con, tid, "Nordvest Teknikk AS")
    assert len(rules.outstanding(con)) == 1

    con.execute("UPDATE reimbursements SET settled_at='2026-08-06'")
    con.commit()
    assert rules.outstanding(con) == []


def test_seed_reference_data_sets_fixed_and_exceptional_treatments(con):
    treat = {r["name"]: r["budget_treatment"]
             for r in con.execute("SELECT name, budget_treatment FROM categories")}
    assert treat["Mortgage - interest"] == "fixed"
    assert treat["Student loan"] == "fixed"
    assert treat["Subscriptions"] == "fixed"
    assert treat["Home & furniture"] == "exceptional"
    assert treat["Groceries"] == "variable"


def test_seed_reference_data_sets_cash_treatments(con):
    cash = {r["name"]: r["cash_treatment"]
            for r in con.execute("SELECT name, cash_treatment FROM categories")}
    assert cash["Mortgage - principal"] == "committed"
    assert cash["Employer loan repayment"] == "committed"
    assert cash["Credit card payment"] == "settlement"
    assert cash["Internal transfer"] == "savings"
