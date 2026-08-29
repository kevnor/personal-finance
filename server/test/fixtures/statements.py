"""Synthetic DNB statements, written as real .xlsx files at test time.

Why this exists
---------------
The three real statements are gitignored, and rightly so -- they are one
person's finances. But guarding them behind `skipif(not CARD_1.exists())`
meant 58 of 337 tests, including *every* ingest-idempotency test, silently
did not run on a fresh clone or in CI. The spec calls those the
highest-value tests in the project ("same file twice yields no duplicates;
overlapping periods yield no duplicates; two identical same-day purchases
are both retained"), so they are exactly the ones that must not be optional.

The invariants those tests assert are structural, not numeric: they are
about identity, idempotency and account scoping, none of which need the real
data. So the rows below reproduce the *shapes* that matter -- a repeated
same-day purchase, a transfer, a Vipps line carrying a counterparty, a
memo-less Vipps line that must be flagged, an invoice carry-over that is not
a transaction -- with invented merchants and invented people.

The real statements remain the anchor for the numbers that are genuinely
about this dataset (181 rows, net 14 084,24, 48 counterparties, the
-13 288,75 loan split); those tests still skip when the statements are
absent, which is correct. See `server/test/test_cli.py`.

Rows are exposed as data, not just baked into a file, so tests can derive
their expectations from the spec rather than hardcoding a number that came
out of running the code.
"""
from __future__ import annotations

import datetime
import zipfile
from dataclasses import dataclass
from pathlib import Path

from server.lib.ingest import dnb_xlsx

EXCEL_EPOCH = datetime.date(1899, 12, 30)


@dataclass(frozen=True)
class Line:
    """One line as it appears in a statement, before any parsing.

    `amount` is signed the way the pipeline reports it -- positive is money
    in -- and is split back into the layout's incoming/outgoing columns by
    `write_xlsx`. `transaction` is False for lines the reader must drop (an
    invoice carry-over balance), so tests can count expected rows from this
    list instead of from a magic number.
    """
    date: str
    description: str
    amount: float
    transaction: bool = True


# --- the card statement ----------------------------------------------------
# Modelled on `transaksjonsliste.xlsx`: opens with an invoice carry-over
# balance, then card purchases and the `Innbetaling` repayments that settle
# them. Each row below earns its place; the comment says which invariant it
# is here to support.
CARD_A: list[Line] = [
    # Not a transaction: a balance carried from the previous invoice. The
    # reader must drop it, which is why `transaction=False`.
    Line("2026-06-30", "Skyldig beløp fra forrige faktura", -4982.80, False),

    # Two genuinely separate purchases, same cafe, same day, same amount --
    # twice over. Keying identity on date+description+amount alone silently
    # discarded one of each pair; both pairs must survive. (The real
    # statement has exactly this shape: two coffees bought separately.)
    Line("2026-06-30", "Baker No Torg, Oslo", -238.00),
    Line("2026-06-30", "Baker No Torg, Oslo", -238.00),
    Line("2026-06-30", "Baker No Torg, Oslo", -119.00),
    Line("2026-06-30", "Baker No Torg, Oslo", -119.00),

    # Card repayments. `^innbetaling$` categorises these as Credit card
    # payment, whose kind is 'transfer' -- so they must land with
    # is_transfer = 1. Repeated, because the real statement repeats them.
    Line("2026-07-01", "Innbetaling", 1350.00),
    Line("2026-07-08", "Innbetaling", 797.00),
    Line("2026-07-15", "Innbetaling", 2156.00),

    # Plain merchants, each matching a built-in rule, none needing review.
    Line("2026-07-02", "Rema Lorenveien, Oslo", -189.90),
    Line("2026-07-02", "Meny Storo, Oslo", -689.20),
    Line("2026-07-03", "Bolt.eu, Tallinn", -149.00),
    Line("2026-07-03", "Narvesen Storo, Oslo", -45.00),
    Line("2026-07-04", "Dominos Hasle, Oslo", -225.00),
    Line("2026-07-05", "Apotek 1 Lorenskog, Oslo", -320.00),
    # Non-ASCII in the description must survive the zip/XML round trip.
    Line("2026-07-06", "Kiwi Grünerløkka, Oslo", -310.50),

    # Vipps lines carrying a recipient: `extract_counterparty` must pull the
    # name out. The first matches a rule (`vy app` -> Public transport);
    # the invented people match none, so they fall through to
    # `Vipps P2P - unspecified` and are flagged for review.
    Line("2026-07-07", "Vipps*VY App, Oslo", -425.00),
    Line("2026-07-07", "Vipps*Aslak Fjellheim, Oslo", -250.00),
    Line("2026-07-08", "Vipps*Ingrid Hovden, Oslo", -180.00),

    # A memo-bearing Vipps transfer in the bank statement's wording: the memo
    # drives the category (`\blading(tpp|ref|\b)` -> Fuel & EV charging) and
    # the trailing-name extractor picks the counterparty off the account
    # number. Note it also swallows the memo token itself -- the extracted
    # name is 'Aslak Fjellheim LadingTpp'. That is current behaviour, not a
    # desired one; it is pinned by a test so a fix is deliberate.
    Line("2026-07-09",
         "Overføring  4790000001 Aslak Fjellheim LadingTpp: Vipps", -300.00),

    # An incoming Vipps share, which must net against its category rather
    # than read as income.
    Line("2026-07-10",
         "Overføring  4790000002 Ingrid Hovden MatTpp: Vipps", 155.00),
]

# A second, non-overlapping card statement -- the "two periods both load
# fully" case. Deliberately shares a merchant with CARD_A but never a
# (date, description, amount) triple, so nothing here is a duplicate.
CARD_B: list[Line] = [
    Line("2026-07-20", "Skyldig beløp fra forrige faktura", -1200.00, False),
    Line("2026-07-21", "Rema Lorenveien, Oslo", -212.40),
    Line("2026-07-22", "Baker No Torg, Oslo", -119.00),
    Line("2026-07-23", "Vipps*Aslak Fjellheim, Oslo", -95.00),
    Line("2026-07-24", "Innbetaling", 500.00),
]

# The bank statement: salary, the fixed bills the budget engine treats as
# commitments, and one loan term for the derived-row split.
BANK: list[Line] = [
    Line("2026-06-30", "Lønn  900112233 Nordvest Teknikk AS", 41113.67),
    Line("2026-07-01", "Fjordkraft AS", -1240.50),
    Line("2026-07-01", "Gjensidige Forsikring", -742.00),
    Line("2026-07-02", "Spotify P2001", -129.00),
    Line("2026-07-03", "Sats Norge AS", -449.00),
    Line("2026-07-05", "Statens Lånekasse", -2635.00),
    # The loan term. `derive.split_loan_term` parses Avdrag/Renter out of the
    # description and books interest, principal and the remaining fee as
    # three derived rows summing back to this charge.
    Line("2026-07-06",
         "Lån 97180512345 Avdrag kr 9.881,49 Renter kr 3.382,26", -13288.75),
    Line("2026-07-07", "Rema Lorenveien, Oslo", -402.10),
    Line("2026-07-08", "Overføring Mellom Egne Konti", -5000.00),
    # Unidentified merchant: matches no rule, is not Vipps, so it must land
    # in Uncategorised and be flagged.
    Line("2026-07-09", "Bjornstad Handel A/S", -298.00),
]


def transactions(lines: list[Line]) -> list[Line]:
    """The lines the reader is expected to return, carry-overs dropped."""
    return [line for line in lines if line.transaction]


# --- writing a real .xlsx --------------------------------------------------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels"'
    ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd'
    '.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application'
    '/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd'
    '.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
    '</Types>')

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.openxml'
    'formats.org/officeDocument/2006/relationships/officeDocument"'
    ' Target="xl/workbook.xml"/></Relationships>')

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<sheets><sheet name="Ark1" sheetId="1" r:id="rId1"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships"/></sheets></workbook>')

_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.openxml'
    'formats.org/officeDocument/2006/relationships/worksheet"'
    ' Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/office'
    'Document/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
    '</Relationships>')

# Header captions, in the real files' wording. Only their presence matters --
# the reader skips row 1 and addresses columns positionally.
HEADERS = {
    dnb_xlsx.BANK: ["Dato", "Forklaring", "Rentedato", "Ut fra konto",
                    "Inn på konto"],
    dnb_xlsx.CARD: ["Dato", "Beløpet gjelder", "Valuta", "Kurs", "Inn", "Ut"],
}


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


def _serial(iso: str) -> int:
    return (datetime.date.fromisoformat(iso) - EXCEL_EPOCH).days


def _column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _grid(lines: list[Line], layout: dnb_xlsx.Layout) -> list[list[str | None]]:
    """Lay the lines out into the layout's columns, header row first."""
    width = max(layout.date, layout.description,
                layout.incoming, layout.outgoing) + 1
    rows: list[list[str | None]] = [list(HEADERS[layout])]
    for line in lines:
        cells: list[str | None] = [None] * width
        cells[layout.date] = str(_serial(line.date))
        cells[layout.description] = line.description
        # DNB writes the magnitude in one of two columns and leaves the other
        # blank; the reader recovers the sign from which column it landed in.
        if line.amount >= 0:
            cells[layout.incoming] = f"{line.amount:.2f}"
        else:
            cells[layout.outgoing] = f"{abs(line.amount):.2f}"
        rows.append(cells)
    return rows


def write_xlsx(path: str | Path, lines: list[Line], layout: dnb_xlsx.Layout,
               shared_strings: bool = True) -> Path:
    """Write `lines` as a DNB-shaped .xlsx and return the path.

    `shared_strings` picks how text is stored. Real exports use a shared
    string table; `inlineStr` is the other form the reader supports, and
    writing both is what keeps that branch covered.
    """
    path = Path(path)
    grid = _grid(lines, layout)

    table: list[str] = []
    index: dict[str, int] = {}
    body: list[str] = []
    for r, row in enumerate(grid, start=1):
        cells: list[str] = []
        for c, value in enumerate(row):
            if value is None:
                continue
            ref = f"{_column(c)}{r}"
            if _is_number(value):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif shared_strings:
                if value not in index:
                    index[value] = len(table)
                    table.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{index[value]}</v></c>')
            else:
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{_escape(value)}</t>'
                    '</is></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')

    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
        '2006/main"><sheetData>' + "".join(body) + "</sheetData></worksheet>")
    strings = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/'
        f'main" count="{len(table)}" uniqueCount="{len(table)}">'
        + "".join(f"<si><t>{_escape(s)}</t></si>" for s in table)
        + "</sst>")

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", _WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        if shared_strings:
            archive.writestr("xl/sharedStrings.xml", strings)
    return path


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def write_input_dir(directory: str | Path) -> Path:
    """Write a full set of statements under the filenames `cli.SOURCES` reads.

    Lets the CLI-level tests -- the legacy guard's refusal path, the
    end-to-end import -- run without the real statements.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_xlsx(directory / "Kontoutskrift.xlsx", BANK, dnb_xlsx.BANK)
    write_xlsx(directory / "transaksjonsliste(1).xlsx", CARD_A, dnb_xlsx.CARD)
    write_xlsx(directory / "transaksjonsliste.xlsx", CARD_B, dnb_xlsx.CARD)
    return directory
