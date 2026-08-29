"""End-to-end `import` and `reconcile`.

Split in two, like test_dnb_xlsx: the pipeline's behaviour is exercised on a
synthetic drop-zone so it runs everywhere, while the assertions that are
genuinely about this dataset -- 181 rows, net 14 084,24, the 48 counterparty
values, the -13 288,75 loan term -- still require the real statements.

Previously a module-level skip covered both kinds, so a fresh clone ran none
of it: not the loan-split idempotency regression, not `reconcile`'s promise
not to write, not the mistyped-path handling.
"""
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from server import cli
from server.lib import store
from server.lib.ingest import dnb_xlsx
from server.test.fixtures import statements

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
MIGRATIONS = ROOT / "db" / "migrations"

needs_statements = pytest.mark.skipif(
    not (INPUT / "Kontoutskrift.xlsx").exists(),
    reason="statements not present")

# Every statement line the fixture declares, across all three files. The loan
# term is replaced by three derived parts that sum back to it, so this is
# also what the pipeline's reported net must come to.
ALL_LINES = (statements.transactions(statements.BANK)
             + statements.transactions(statements.CARD_A)
             + statements.transactions(statements.CARD_B))
SOURCE_ROWS = len(ALL_LINES)
NET = round(sum(line.amount for line in ALL_LINES), 2)


@pytest.fixture
def input_dir(tmp_path):
    return statements.write_input_dir(tmp_path / "input")


# -- the pipeline ----------------------------------------------------------

def test_import_reports_what_it_wrote(tmp_path, input_dir):
    result = cli.build(tmp_path / "t.db", input_dir, MIGRATIONS)
    assert result["inserted"] == SOURCE_ROWS
    assert result["skipped"] == 0
    # One loan term is replaced by three derived parts, so the stored row
    # count is the source rows minus that line, plus its three parts.
    assert result["count"] == SOURCE_ROWS - 1 + 3


def test_splitting_the_loan_term_conserves_the_net(tmp_path, input_dir):
    """The three derived parts replace the source row, so if they did not sum
    back to it the dataset's net would move -- silently, since nothing else
    would change."""
    result = cli.build(tmp_path / "t.db", input_dir, MIGRATIONS)
    assert result["net"] == NET


def test_pipeline_is_idempotent_across_runs(tmp_path, input_dir):
    db = tmp_path / "t.db"
    first = cli.build(db, input_dir, MIGRATIONS)
    second = cli.build(db, input_dir, MIGRATIONS)
    assert second["inserted"] == 0
    assert second["skipped"] == first["inserted"]
    assert second["count"] == first["count"]
    assert second["net"] == first["net"]


def test_counterparty_is_populated_and_repaired(tmp_path, input_dir):
    """The standalone script extracted counterparty values; the app pipeline
    stored 0, because store never called extract_counterparty. And a database
    imported before the wiring existed has NULL for every row, which
    re-importing cannot fix -- those rows are skipped as already present --
    so import repairs them rather than leaving the column empty."""
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    con = store.connect(db)
    expected = con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0]
    assert expected > 0

    con.execute("UPDATE transactions SET counterparty = NULL")
    con.commit()
    con.close()

    cli.build(db, input_dir, MIGRATIONS)
    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == expected


def test_mortgage_row_is_split_into_three_derived_rows(tmp_path, input_dir):
    cli.build(tmp_path / "t.db", input_dir, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    rows = list(con.execute(
        "SELECT c.name, t.amount FROM transactions t"
        " JOIN categories c ON c.id = t.category_id"
        " WHERE t.is_derived = 1"))
    assert {r["name"] for r in rows} == {
        "Mortgage - interest", "Mortgage - principal", "Mortgage - fees"}
    loan = next(line for line in statements.BANK if "Avdrag" in line.description)
    assert round(sum(r["amount"] for r in rows), 2) == loan.amount


def test_no_unsplit_mortgage_row_remains(tmp_path, input_dir):
    cli.build(tmp_path / "t.db", input_dir, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    assert con.execute(
        "SELECT COUNT(*) FROM transactions t JOIN categories c"
        " ON c.id = t.category_id WHERE c.name = 'Mortgage & loan'"
    ).fetchone()[0] == 0


def test_loan_split_inserts_nothing_further_on_a_second_run(
        tmp_path, input_dir):
    """Regression: an earlier design inserted the raw loan row and then
    deleted it in favour of its derived parts, which made the row invisible
    to upsert_transactions' identity check (is_derived = 0 only) and caused
    it to be silently reinserted and resplit on every subsequent run. A row
    count alone would not catch a regression that inserts and deletes in
    equal measure, and the set-based category assertion above would not
    notice six derived rows where three are expected, so this checks both the
    reported "derived" count and the actual row count directly.
    """
    db = tmp_path / "t.db"
    first = cli.build(db, input_dir, MIGRATIONS)
    second = cli.build(db, input_dir, MIGRATIONS)
    assert first["derived"] == 3
    assert second["derived"] == 0

    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(*) FROM transactions WHERE is_derived = 1"
    ).fetchone()[0] == 3


# -- reconcile must not write ---------------------------------------------

def test_reconcile_reports_without_inserting_anything(tmp_path, input_dir):
    """`reconcile` shared every line of `import` -- args.command was never
    read -- so on a fresh database it inserted rows and exited 0."""
    db = tmp_path / "t.db"
    built = cli.build(db, input_dir, MIGRATIONS)
    before = db.stat().st_mtime_ns

    result = cli.reconcile(db)
    assert result["count"] == built["count"]
    assert result["net"] == built["net"]
    assert result["needs_review"] > 0
    assert db.stat().st_mtime_ns == before


def test_reconcile_on_a_fresh_database_errors_instead_of_building_one(tmp_path):
    """It used to create and populate the database it was asked to report on.
    Reporting on rows you just inserted is not reconciliation."""
    db = tmp_path / "absent.db"
    assert cli.main(["reconcile", "--db", str(db)]) == 2
    assert not db.exists()


def test_reconcile_opens_the_database_read_only(tmp_path, input_dir):
    """The promise is enforced by SQLite, not by reconcile's good intentions:
    any write on this connection raises."""
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    con = store.connect(db, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("DELETE FROM transactions")


def test_reconcile_honours_expect_net(tmp_path, input_dir, capsys):
    db = tmp_path / "t.db"
    built = cli.build(db, input_dir, MIGRATIONS)
    assert cli.main(["reconcile", "--db", str(db),
                     "--expect-net", str(built["net"])]) == 0
    assert cli.main(["reconcile", "--db", str(db),
                     "--expect-net", "999.0"]) == 1
    assert "MISMATCH" in capsys.readouterr().out
    # ... and still wrote nothing while doing it.
    assert cli.reconcile(db)["count"] == built["count"]


def test_reconcile_takes_no_input_argument(tmp_path):
    """It reads no statements, so offering --input would imply it might."""
    with pytest.raises(SystemExit):
        cli.main(["reconcile", "--db", str(tmp_path / "t.db"),
                  "--input", str(tmp_path)])


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
    statements.write_xlsx(partial / "Kontoutskrift.xlsx",
                          statements.BANK, dnb_xlsx.BANK)
    result = cli.build(tmp_path / "t.db", partial, MIGRATIONS)
    bank_rows = len(statements.transactions(statements.BANK))
    assert result["count"] == bank_rows - 1 + 3     # loan term split in three


# -- this dataset's own figures, on the real statements --------------------

@needs_statements
def test_full_pipeline_reproduces_the_known_dataset(tmp_path):
    result = cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    assert result["count"] == 181
    assert result["net"] == 14084.24


@needs_statements
def test_real_import_is_idempotent_and_holds_the_known_net(tmp_path):
    db = tmp_path / "t.db"
    first = cli.build(db, INPUT, MIGRATIONS)
    second = cli.build(db, INPUT, MIGRATIONS)
    assert second["inserted"] == 0
    assert second["skipped"] == first["inserted"]
    assert second["count"] == 181
    assert second["net"] == 14084.24


@needs_statements
def test_import_populates_counterparty_for_the_same_48_rows_as_the_legacy_db(
        tmp_path):
    """The standalone script extracted 48 counterparty values; the count is
    the anchor, and the extraction itself is covered in test_upsert.py."""
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    con = store.connect(db)
    assert con.execute(
        "SELECT COUNT(counterparty) FROM transactions").fetchone()[0] == 48


@needs_statements
def test_real_mortgage_term_sums_back_to_the_known_charge(tmp_path):
    cli.build(tmp_path / "t.db", INPUT, MIGRATIONS)
    con = store.connect(tmp_path / "t.db")
    rows = list(con.execute(
        "SELECT t.amount FROM transactions t WHERE t.is_derived = 1"))
    assert round(sum(r["amount"] for r in rows), 2) == -13288.75


@needs_statements
def test_real_reconcile_reports_the_known_review_queue(tmp_path):
    db = tmp_path / "t.db"
    cli.build(db, INPUT, MIGRATIONS)
    result = cli.reconcile(db)
    assert result["count"] == 181
    assert result["net"] == 14084.24
    assert result["needs_review"] == 29


# -- budget: the engine's first production caller --------------------------

def test_budget_reports_the_envelope_for_a_given_day(tmp_path, input_dir):
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    summary = cli.budget_report(db, date(2026, 7, 15))
    assert summary.day == date(2026, 7, 15)
    assert summary.week_start == date(2026, 7, 13)
    assert summary.figures.week_envelope > 0
    assert sorted(summary.pools) == ["2026-07"]


def test_budget_writes_nothing(tmp_path, input_dir):
    """Same promise as reconcile, enforced the same way -- the connection is
    opened mode=ro, so a stray write raises rather than succeeding quietly."""
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    before = db.stat().st_mtime_ns
    cli.budget_report(db, date(2026, 7, 15))
    assert db.stat().st_mtime_ns == before


def test_budget_on_a_fresh_database_errors_instead_of_building_one(tmp_path):
    db = tmp_path / "absent.db"
    assert cli.main(["budget", "--db", str(db)]) == 2
    assert not db.exists()


def test_budget_command_prints_both_months_for_a_straddling_week(
        tmp_path, input_dir, capsys):
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    assert cli.main(["budget", "--db", str(db), "--date", "2026-06-30"]) == 0
    out = capsys.readouterr().out
    assert "2026-06:" in out and "2026-07:" in out


def test_budget_rejects_a_malformed_date(tmp_path, input_dir):
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    with pytest.raises(SystemExit):
        cli.main(["budget", "--db", str(db), "--date", "not-a-date"])


def test_budget_on_a_database_with_no_config_reports_rather_than_crashing(
        tmp_path, input_dir, capsys):
    """`import` seeds budget_config, but a database built another way has
    none, and load_config raises. That is the user's to fix, so it gets the
    same one-line message as a mistyped path."""
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    con = store.connect(db)
    con.execute("DELETE FROM budget_config")
    con.commit()
    con.close()

    assert cli.main(["budget", "--db", str(db)]) == 2
    assert "ERROR" in capsys.readouterr().out


def test_an_edited_migration_is_reported_rather_than_crashing(
        tmp_path, input_dir, capsys):
    db = tmp_path / "t.db"
    cli.build(db, input_dir, MIGRATIONS)
    con = store.connect(db)
    con.execute("UPDATE schema_migrations SET checksum = 'tampered'"
                " WHERE name = '001_baseline.sql'")
    con.commit()
    con.close()

    code = cli.main(["import", "--db", str(db), "--input", str(input_dir)])
    assert code == 2
    assert "ERROR" in capsys.readouterr().out
