import sqlite3
from pathlib import Path

import pytest

from server import cli
from server.lib import store

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
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == 48

    # A database imported before the wiring existed has NULL for every row,
    # and re-importing skips them as already present -- so import repairs
    # them rather than leaving the column permanently empty.
    con.execute("UPDATE transactions SET counterparty = NULL")
    con.commit()
    con.close()
    cli.build(db, INPUT, MIGRATIONS)
    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == 48


def test_mortgage_row_is_split_into_three_derived_rows(tmp_path):
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
    db = tmp_path / "t.db"
    first = cli.build(db, INPUT, MIGRATIONS)
    second = cli.build(db, INPUT, MIGRATIONS)
    assert first["derived"] == 3
    assert second["derived"] == 0

    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(*) FROM transactions WHERE is_derived = 1"
    ).fetchone()[0] == 3


# -- reconcile must not write ---------------------------------------------

def test_reconcile_reports_without_inserting_anything(tmp_path):
    """`reconcile` shared every line of `import` -- args.command was never
    read -- so on a fresh database it inserted 179 rows and exited 0."""
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    before = db.stat().st_mtime_ns

    result = cli.reconcile(db)
    assert result["count"] == 181
    assert result["net"] == 14084.24
    assert result["needs_review"] == 29
    assert db.stat().st_mtime_ns == before


def test_reconcile_on_a_fresh_database_errors_instead_of_building_one(tmp_path):
    """It used to create and populate the database it was asked to report on.
    Reporting on 179 rows you just inserted is not reconciliation."""
    db = tmp_path / "absent.db"
    assert cli.main(["reconcile", "--db", str(db)]) == 2
    assert not db.exists()


def test_reconcile_opens_the_database_read_only(tmp_path):
    """The promise is enforced by SQLite, not by reconcile's good intentions:
    any write on this connection raises."""
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    con = store.connect(db, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("DELETE FROM transactions")


def test_reconcile_honours_expect_net(tmp_path, capsys):
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    assert cli.main(["reconcile", "--db", str(db),
                     "--expect-net", "14084.24"]) == 0
    assert cli.main(["reconcile", "--db", str(db),
                     "--expect-net", "999.0"]) == 1
    assert "MISMATCH" in capsys.readouterr().out
    # ... and still wrote nothing while doing it.
    assert cli.reconcile(db)["count"] == 181


def test_reconcile_takes_no_input_argument(tmp_path):
    """It reads no statements, so offering --input would imply it might."""
    with pytest.raises(SystemExit):
        cli.main(["reconcile", "--db", str(tmp_path / "t.db"),
                  "--input", str(INPUT)])


# -- a mistyped --input path is an error, not "nothing new" ----------------

def test_a_missing_input_directory_is_an_error(tmp_path):
    """It printed "0 transactions, net 0.00" and exited 0, which reads as
    "no new statements" rather than "you mistyped the path"."""
    with pytest.raises(FileNotFoundError):
        cli.build(tmp_path / "t.db", tmp_path / "nope", MIGRATIONS)


def test_a_missing_input_directory_exits_nonzero(tmp_path, capsys):
    code = cli.main(["import", "--db", str(tmp_path / "t.db"),
                     "--input", str(tmp_path / "nope")])
    assert code == 2
    assert "ERROR" in capsys.readouterr().out


def test_an_individually_absent_statement_is_still_skipped_quietly(tmp_path):
    """Only some of the three statements may have been dropped in; that is
    normal and must stay a no-op rather than an error."""
    partial = tmp_path / "input"
    partial.mkdir()
    (partial / "Kontoutskrift.xlsx").write_bytes(
        (INPUT / "Kontoutskrift.xlsx").read_bytes())
    result = cli.build(tmp_path / "t.db", partial, MIGRATIONS)
    assert result["count"] == 125          # bank statement only, loan split
