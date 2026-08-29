"""The xlsx reader.

Split in two: the reader's mechanics are exercised against a synthetic
statement so they run everywhere, while the tests that assert this dataset's
own figures still require the real statements.
"""
from pathlib import Path

import pytest

from server.lib.ingest import dnb_xlsx
from server.test.fixtures import statements

INPUT = Path(__file__).resolve().parents[2] / "input"

BANK_FILE = INPUT / "Kontoutskrift.xlsx"
CARD_1 = INPUT / "transaksjonsliste(1).xlsx"
CARD_2 = INPUT / "transaksjonsliste.xlsx"

needs_statements = pytest.mark.skipif(
    not BANK_FILE.exists(), reason="statements not present")


# --- reader mechanics, on the synthetic statement --------------------------

@pytest.fixture
def bank(tmp_path):
    return statements.write_xlsx(
        tmp_path / "bank.xlsx", statements.BANK, dnb_xlsx.BANK)


@pytest.mark.parametrize("shared_strings", [True, False])
def test_both_string_encodings_read_identically(tmp_path, shared_strings):
    """Real exports use a shared string table; `inlineStr` is the other form
    the reader supports. Reading both is what keeps that branch honest."""
    path = statements.write_xlsx(
        tmp_path / f"card-{shared_strings}.xlsx", statements.CARD_A,
        dnb_xlsx.CARD, shared_strings=shared_strings)
    rows = dnb_xlsx.read_statement(path, dnb_xlsx.CARD)
    assert [(r.date, r.description, r.amount) for r in rows] == [
        (line.date, line.description, line.amount)
        for line in statements.transactions(statements.CARD_A)]


def test_invoice_carryover_rows_are_excluded(tmp_path):
    """`Skyldig beløp fra forrige faktura` opens each card statement. It is
    the balance brought forward, not a transaction, and counting it would
    double the invoice."""
    path = statements.write_xlsx(
        tmp_path / "card.xlsx", statements.CARD_A, dnb_xlsx.CARD)
    rows = dnb_xlsx.read_statement(path, dnb_xlsx.CARD)
    assert len(rows) == len(statements.transactions(statements.CARD_A))
    assert len(rows) == len(statements.CARD_A) - 1
    for row in rows:
        assert "forrige faktura" not in row.description.lower()


def test_excel_serial_converted_to_iso_date(bank):
    rows = dnb_xlsx.read_statement(bank, dnb_xlsx.BANK)
    assert rows[0].date == "2026-06-30"
    assert all(len(r.date) == 10 and r.date[4] == "-" for r in rows)


def test_outgoing_is_negative_and_incoming_positive(bank):
    rows = dnb_xlsx.read_statement(bank, dnb_xlsx.BANK)
    by_desc = {r.description: r.amount for r in rows}
    assert by_desc["Lønn  900112233 Nordvest Teknikk AS"] == 41113.67
    grocery = next(v for k, v in by_desc.items() if "Rema Lorenveien" in k)
    assert grocery < 0


def test_reading_a_statement_under_the_wrong_layout_loses_the_outgoings(
        tmp_path):
    """The two layouts agree on the incoming column (4) and disagree on the
    outgoing one -- 3 for the bank, 5 for the card. So a file read under the
    wrong layout keeps its credits and silently reads every debit as 0,00
    rather than failing. Nothing in the reader can detect that; the layout is
    the caller's assertion about the file, which is why `cli.SOURCES` pairs
    each filename with one explicitly."""
    path = statements.write_xlsx(
        tmp_path / "bank.xlsx", statements.BANK, dnb_xlsx.BANK)

    correct = {r.description: r.amount
               for r in dnb_xlsx.read_statement(path, dnb_xlsx.BANK)}
    wrong = {r.description: r.amount
             for r in dnb_xlsx.read_statement(path, dnb_xlsx.CARD)}

    salary = "Lønn  900112233 Nordvest Teknikk AS"
    assert correct[salary] == wrong[salary] == 41113.67   # shared column
    assert correct["Fjordkraft AS"] == -1240.50
    assert wrong["Fjordkraft AS"] == 0.0                  # debit column missed


def test_norwegian_characters_survive_parsing(bank):
    rows = dnb_xlsx.read_statement(bank, dnb_xlsx.BANK)
    assert any("Lånekasse" in r.description for r in rows)
    assert any("ø" in r.description or "æ" in r.description for r in rows)


def test_source_row_is_one_based_and_unique(bank):
    rows = dnb_xlsx.read_statement(bank, dnb_xlsx.BANK)
    numbers = [r.source_row for r in rows]
    assert len(set(numbers)) == len(numbers)
    assert min(numbers) >= 2  # row 1 is the header


def test_rows_missing_a_date_or_description_are_skipped(tmp_path):
    """Statement exports carry trailing blank rows and the odd sub-total with
    no date; neither is a transaction."""
    lines = list(statements.CARD_B)
    lines.append(statements.Line("2026-07-25", "", -10.0))
    path = statements.write_xlsx(tmp_path / "gaps.xlsx", lines, dnb_xlsx.CARD)
    rows = dnb_xlsx.read_statement(path, dnb_xlsx.CARD)
    assert len(rows) == len(statements.transactions(statements.CARD_B))


# --- this dataset's own figures, on the real statements --------------------

@needs_statements
def test_bank_statement_row_count():
    assert len(dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)) == 123


@needs_statements
def test_card_statements_exclude_invoice_carryover_rows():
    # Each card file opens with 'Skyldig beløp fra forrige faktura', which is
    # a balance, not a transaction. 44 and 14 data rows respectively.
    assert len(dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)) == 43
    assert len(dnb_xlsx.read_statement(CARD_2, dnb_xlsx.CARD)) == 13
    for path in (CARD_1, CARD_2):
        for row in dnb_xlsx.read_statement(path, dnb_xlsx.CARD):
            assert "forrige faktura" not in row.description.lower()


@needs_statements
def test_bank_and_card_totals_match_the_known_net():
    total = sum(r.amount for r in
                dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK))
    total += sum(r.amount for r in
                 dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD))
    total += sum(r.amount for r in
                 dnb_xlsx.read_statement(CARD_2, dnb_xlsx.CARD))
    assert round(total, 2) == 14084.24
