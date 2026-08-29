"""Statement upload: preview, then commit.

Uses the same synthetic statements as the ingest tests, so what these assert
about the API is the same thing the CLI tests assert about the pipeline.
"""
from __future__ import annotations

import io

from server.lib.ingest import dnb_xlsx
from server.test.fixtures import statements

BANK = "Bankkonto"
CARD = "Kredittkort"


def upload(lines, layout=dnb_xlsx.CARD, name="statement.xlsx"):
    """The statement as an in-memory multipart file part."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        path = statements.write_xlsx(Path(directory) / name, lines, layout)
        payload = path.read_bytes()
    return {"file": (name, io.BytesIO(payload),
                     "application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet")}


CARD_ROWS = len(statements.transactions(statements.CARD_A))


# -- preview ----------------------------------------------------------------

def test_preview_reports_what_committing_would_do(client):
    response = client.post("/api/imports/preview",
                           files=upload(statements.CARD_A),
                           data={"account": CARD})
    assert response.status_code == 200
    body = response.json()
    assert body["account"] == CARD
    assert body["total"] == CARD_ROWS
    assert body["new"] == CARD_ROWS
    assert body["existing"] == 0
    assert body["needs_review"] > 0
    assert len(body["rows"]) == CARD_ROWS


def test_preview_writes_nothing(client):
    """The spec requires a preview before a statement upload is committed --
    "a silent half-duplicating import is painful to unpick" -- so this one
    must genuinely be a dry run."""
    client.post("/api/imports/preview", files=upload(statements.CARD_A),
                data={"account": CARD})
    assert client.get("/api/transactions").json() == []


def test_preview_recognises_rows_already_imported(client):
    client.post("/api/imports", files=upload(statements.CARD_A),
                data={"account": CARD})
    body = client.post("/api/imports/preview",
                       files=upload(statements.CARD_A),
                       data={"account": CARD}).json()
    assert body["new"] == 0
    assert body["existing"] == CARD_ROWS


def test_preview_and_commit_agree_on_what_is_new(client):
    """They run the same identity computation on purpose: a preview that
    disagreed with the commit that followed would be worse than none."""
    preview = client.post("/api/imports/preview",
                          files=upload(statements.CARD_A),
                          data={"account": CARD}).json()
    committed = client.post("/api/imports", files=upload(statements.CARD_A),
                            data={"account": CARD}).json()
    assert preview["new"] == committed["inserted"]
    assert preview["existing"] == committed["skipped"]


def test_preview_carries_the_category_each_row_would_get(client):
    rows = client.post("/api/imports/preview",
                       files=upload(statements.CARD_A),
                       data={"account": CARD}).json()["rows"]
    by_description = {r["description"]: r for r in rows}
    assert by_description["Rema Lorenveien, Oslo"]["category"] == "Groceries"
    assert by_description["Innbetaling"]["category"] == "Credit card payment"


# -- commit -----------------------------------------------------------------

def test_committing_inserts_the_rows(client):
    response = client.post("/api/imports", files=upload(statements.CARD_A),
                           data={"account": CARD})
    assert response.status_code == 201
    assert response.json()["inserted"] == CARD_ROWS
    assert len(client.get(
        f"/api/transactions?limit={CARD_ROWS}").json()) == CARD_ROWS


def test_committing_the_same_file_twice_inserts_nothing_the_second_time(
        client):
    """Additive and idempotent, like every other ingest path -- so a user
    unsure whether they already uploaded it can just do it again."""
    client.post("/api/imports", files=upload(statements.CARD_A),
                data={"account": CARD})
    second = client.post("/api/imports", files=upload(statements.CARD_A),
                         data={"account": CARD}).json()
    assert second["inserted"] == 0
    assert second["skipped"] == CARD_ROWS


def test_a_bank_statement_loan_term_is_split_on_upload(client):
    """The loan-term partition is shared with the CLI (server/lib/importer.py)
    precisely so the API cannot get it wrong separately."""
    response = client.post("/api/imports",
                           files=upload(statements.BANK, dnb_xlsx.BANK),
                           data={"account": BANK})
    assert response.json()["derived"] == 3

    rows = client.get("/api/transactions?limit=500").json()
    derived = [r for r in rows if r["is_derived"]]
    assert {r["category"] for r in derived} == {
        "Mortgage - interest", "Mortgage - principal", "Mortgage - fees"}


def test_the_upload_path_and_the_cli_produce_the_same_rows(client, tmp_path,
                                                           settings):
    """Two doors into one pipeline. If they disagree, the same file produces
    different databases depending on how it was imported."""
    from server import cli
    from server.lib import store

    client.post("/api/imports", files=upload(statements.BANK, dnb_xlsx.BANK),
                data={"account": BANK})
    client.post("/api/imports", files=upload(statements.CARD_A),
                data={"account": CARD})
    client.post("/api/imports", files=upload(statements.CARD_B),
                data={"account": CARD})

    reference = tmp_path / "cli.db"
    cli.build(reference, statements.write_input_dir(tmp_path / "input"),
              settings.migrations_dir)

    def fingerprints(path):
        con = store.connect(path, read_only=True)
        try:
            return sorted(
                (r["date"], r["description"], r["amount"], r["is_derived"])
                for r in con.execute(
                    "SELECT date, description, amount, is_derived"
                    " FROM transactions"))
        finally:
            con.close()

    # The CLI additionally applies server/corrections.py, which names rows
    # this synthetic dataset does not contain, so the row sets are comparable.
    assert fingerprints(settings.db_path) == fingerprints(reference)


# -- rejections -------------------------------------------------------------

def test_an_unknown_account_is_rejected_and_names_the_known_ones(client):
    response = client.post("/api/imports", files=upload(statements.CARD_A),
                           data={"account": "Nowhere"})
    assert response.status_code == 422
    assert "Bankkonto" in response.json()["detail"]


def test_a_file_that_is_not_a_spreadsheet_is_422_not_500(client):
    response = client.post(
        "/api/imports",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"account": CARD})
    assert response.status_code == 422
    assert "could not read" in response.json()["detail"]


def test_an_empty_file_is_rejected(client):
    response = client.post(
        "/api/imports",
        files={"file": ("empty.xlsx", io.BytesIO(b""), "application/octet-stream")},
        data={"account": CARD})
    assert response.status_code == 422


def test_the_account_is_required(client):
    assert client.post("/api/imports",
                       files=upload(statements.CARD_A)).status_code == 422


def test_an_oversized_upload_is_refused(client, monkeypatch):
    """The file is read into memory to be parsed, so an unbounded upload is
    an unbounded allocation."""
    from server.routes import imports
    monkeypatch.setattr(imports, "MAX_UPLOAD_BYTES", 10)
    response = client.post("/api/imports", files=upload(statements.CARD_A),
                           data={"account": CARD})
    assert response.status_code == 413


def test_the_layout_follows_the_account_kind(client):
    """Bank and card statements disagree about which column holds money out,
    and the reader cannot tell them apart -- read under the wrong layout a
    file keeps its credits and reads every debit as 0,00. So uploading the
    bank statement as a card statement must not silently produce zeroes."""
    client.post("/api/imports", files=upload(statements.BANK, dnb_xlsx.BANK),
                data={"account": BANK})
    rows = client.get("/api/transactions?limit=500").json()
    debits = [r for r in rows if r["amount"] < 0]
    assert debits, "every outgoing row was read as 0,00"
