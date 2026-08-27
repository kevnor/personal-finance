from pathlib import Path

import pytest

from server.lib.ingest import dnb_xlsx

INPUT = Path(__file__).resolve().parents[2] / "input"

BANK_FILE = INPUT / "Kontoutskrift.xlsx"
CARD_1 = INPUT / "transaksjonsliste(1).xlsx"
CARD_2 = INPUT / "transaksjonsliste.xlsx"

pytestmark = pytest.mark.skipif(
    not BANK_FILE.exists(), reason="statements not present")


def test_bank_statement_row_count():
    assert len(dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)) == 123


def test_card_statements_exclude_invoice_carryover_rows():
    # Each card file opens with 'Skyldig beløp fra forrige faktura', which is
    # a balance, not a transaction. 44 and 14 data rows respectively.
    assert len(dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD)) == 43
    assert len(dnb_xlsx.read_statement(CARD_2, dnb_xlsx.CARD)) == 13
    for path in (CARD_1, CARD_2):
        for row in dnb_xlsx.read_statement(path, dnb_xlsx.CARD):
            assert "forrige faktura" not in row.description.lower()


def test_excel_serial_converted_to_iso_date():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    assert rows[0].date == "2026-06-30"
    assert all(len(r.date) == 10 and r.date[4] == "-" for r in rows)


def test_outgoing_is_negative_and_incoming_positive():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    by_desc = {r.description: r.amount for r in rows}
    assert by_desc["Lønn  900112233 Nordvest Teknikk AS"] == 41113.67
    grocery = next(v for k, v in by_desc.items() if "Rema Lorenveien" in k)
    assert grocery < 0


def test_norwegian_characters_survive_parsing():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    assert any("Løren" in r.description for r in rows)
    assert any("ø" in r.description or "æ" in r.description for r in rows)


def test_source_row_is_one_based_and_unique():
    rows = dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK)
    numbers = [r.source_row for r in rows]
    assert len(set(numbers)) == len(numbers)
    assert min(numbers) >= 2  # row 1 is the header


def test_bank_and_card_totals_match_the_known_net():
    total = sum(r.amount for r in
                dnb_xlsx.read_statement(BANK_FILE, dnb_xlsx.BANK))
    total += sum(r.amount for r in
                 dnb_xlsx.read_statement(CARD_1, dnb_xlsx.CARD))
    total += sum(r.amount for r in
                 dnb_xlsx.read_statement(CARD_2, dnb_xlsx.CARD))
    assert round(total, 2) == 14084.24
