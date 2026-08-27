"""Statement ingest: one module per source format, one shared row shape.

`RawRow` lives here rather than in any format reader because it is the
contract the whole pipeline is built on: the spec's ingest design has four
sources (manual entry, statement upload, bulk API, and a later bank fetch)
normalising to one row shape before categorisation, so the bank fetch is a
fourth source rather than a second pipeline. With it defined inside
dnb_xlsx.py, both store.py and fingerprint.py imported the persistence and
identity layers' central type from a DNB spreadsheet reader — and a second
format reader would have had to import it from the first.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RawRow"]


@dataclass(frozen=True)
class RawRow:
    """One normalised statement line.

    `amount` is signed NOK: positive is money in, negative is money out.
    `source_row` is the 1-based line in the source document, kept for human
    audit only — row identity is the content fingerprint, deliberately not
    position (see ingest/fingerprint.py).
    """
    date: str
    description: str
    amount: float
    source_row: int
