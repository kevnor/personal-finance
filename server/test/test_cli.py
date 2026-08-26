from pathlib import Path

import pytest

from server import cli

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
MIGRATIONS = ROOT / "db" / "migrations"

pytestmark = pytest.mark.skipif(
    not (INPUT / "Kontoutskrift.xlsx").exists(),
    reason="statements not present")


def test_full_pipeline_reproduces_the_known_dataset(tmp_path):
    result = cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    assert result["count"] == 181
    assert result["net"] == 14084.24


def test_pipeline_is_idempotent_across_runs(tmp_path):
    db = tmp_path / "t.db"
    first = cli.build(db, INPUT, MIGRATIONS)
    second = cli.build(db, INPUT, MIGRATIONS)
    assert second["inserted"] == 0
    assert second["skipped"] == first["inserted"]
    assert second["count"] == 181
    assert second["net"] == 14084.24


def test_import_populates_counterparty_for_the_same_48_rows_as_the_legacy_db(
        tmp_path):
    """The standalone script extracted 48 counterparty values; the app
    pipeline stored 0, because store never called extract_counterparty. The
    count is the anchor: passing no extractor leaves every row NULL, and the
    unit test in test_upsert.py checks the extracted values themselves."""
    from server.lib import store
    cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == 48


def test_mortgage_row_is_split_into_three_derived_rows(tmp_path):
    from server.lib import store
    cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    rows = list(con.execute(
        "SELECT c.name, t.amount FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE t.is_derived = 1"))
    assert {r["name"] for r in rows} == {
        "Mortgage - interest", "Mortgage - principal", "Mortgage - fees"}
    assert round(sum(r["amount"] for r in rows), 2) == -13288.75


def test_no_unsplit_mortgage_row_remains(tmp_path):
    from server.lib import store
    cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    assert con.execute(
        "SELECT COUNT(*) FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE c.name = 'Mortgage & loan'"
    ).fetchone()[0] == 0


def test_loan_split_inserts_nothing_further_on_a_second_run(tmp_path):
    """Regression test for the bug fixed in this task: an earlier design
    inserted the raw loan row and then deleted it in favour of its derived
    parts, which made the row invisible to upsert_transactions' identity
    check (is_derived = 0 only) and caused it to be silently reinserted and
    resplit on every subsequent run. `assert second["count"] == 181` alone
    would not catch a regression that inserts and deletes in equal measure,
    and the set-based category assertion above would not notice six derived
    rows where three are expected, so this checks both the reported
    "derived" count and the actual row count directly.
    """
    from server.lib import store
    db = tmp_path / "t.db"
    first = cli.build(db, INPUT, MIGRATIONS)
    second = cli.build(db, INPUT, MIGRATIONS)
    assert first["derived"] == 3
    assert second["derived"] == 0

    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(*) FROM transactions WHERE is_derived = 1"
    ).fetchone()[0] == 3
