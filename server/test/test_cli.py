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
