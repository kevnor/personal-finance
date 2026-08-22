"""Read DNB xlsx statement exports into normalised rows.

Hand-rolled on zipfile + ElementTree: openpyxl is not installed, and the
parsing need is narrow (one sheet, no formulas, no styling).

Knows about spreadsheet layouts. Knows nothing about categories.
"""
from __future__ import annotations

import datetime
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXCEL_EPOCH = datetime.date(1899, 12, 30)
CARRYOVER_RE = re.compile(r"skyldig bel.p fra forrige faktura", re.I)


@dataclass(frozen=True)
class Layout:
    """Zero-based column positions for one statement format."""
    date: int
    description: int
    incoming: int
    outgoing: int


# Kontoutskrift: Dato | Forklaring | Rentedato | Ut fra konto | Inn på konto
BANK = Layout(date=0, description=1, incoming=4, outgoing=3)
# Transaksjonsliste: Dato | Beløpet gjelder | Valuta | Kurs | Inn | Ut
CARD = Layout(date=0, description=1, incoming=4, outgoing=5)


@dataclass(frozen=True)
class RawRow:
    date: str
    description: str
    amount: float
    source_row: int


def _column_index(ref: str) -> int:
    n = 0
    for char in re.match(r"([A-Z]+)", ref).group(1):
        n = n * 26 + ord(char) - 64
    return n - 1


def _sheet_rows(path: str | Path) -> list[list[str]]:
    archive = zipfile.ZipFile(path)

    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    rows: list[list[str]] = []
    sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter(f"{NS}row"):
        cells: dict[int, str] = {}
        for cell in row.findall(f"{NS}c"):
            kind = cell.get("t")
            value = cell.find(f"{NS}v")
            inline = cell.find(f"{NS}is")
            if kind == "inlineStr" and inline is not None:
                text = "".join(t.text or "" for t in inline.iter(f"{NS}t"))
            elif kind == "s" and value is not None:
                text = shared[int(value.text)]
            elif value is not None:
                text = value.text
            else:
                continue
            cells[_column_index(cell.get("r"))] = text
        rows.append([cells.get(i) or "" for i in range(max(cells) + 1)]
                    if cells else [])
    return rows


def _to_iso(serial: str) -> str:
    return (EXCEL_EPOCH + datetime.timedelta(days=int(float(serial)))).isoformat()


def _to_float(text: str) -> float:
    text = (text or "").strip()
    return float(text) if text else 0.0


def read_statement(path: str | Path, layout: Layout) -> list[RawRow]:
    width = max(layout.date, layout.description,
                layout.incoming, layout.outgoing) + 1

    out: list[RawRow] = []
    for lineno, raw in enumerate(_sheet_rows(path), start=1):
        if lineno == 1:
            continue                                    # header
        row = raw + [""] * (width - len(raw))
        description = (row[layout.description] or "").strip()
        if not description or not (row[layout.date] or "").strip():
            continue
        if CARRYOVER_RE.search(description):            # balance, not a transaction
            continue
        amount = round(_to_float(row[layout.incoming])
                       - _to_float(row[layout.outgoing]), 2)
        out.append(RawRow(_to_iso(row[layout.date]), description,
                          amount, lineno))
    return out
