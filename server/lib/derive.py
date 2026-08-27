"""Expand itemised statement rows into their component parts.

A loan term line states principal and interest inside its own description.
Interest and any fee are real expenses; principal is debt repayment, booked
as a transfer so it stays out of spending reports while still reducing the
budget pool (see budget.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

AVDRAG_RE = re.compile(r"avdrag\s+kr\s*([\d.]+,\d{2})", re.I)
RENTER_RE = re.compile(r"renter\s+kr\s*([\d.]+,\d{2})", re.I)


@dataclass(frozen=True)
class DerivedRow:
    description: str
    amount: float
    category: str


def _nok(text: str) -> float:
    """Parse Norwegian number format: '3.407,26' -> 3407.26."""
    return float(text.replace(".", "").replace(",", "."))


def split_loan_term(description: str, amount: float) -> list[DerivedRow]:
    avdrag = AVDRAG_RE.search(description)
    renter = RENTER_RE.search(description)
    if not (avdrag and renter):
        return []

    principal = _nok(avdrag.group(1))
    interest = _nok(renter.group(1))
    fee = round(abs(amount) - principal - interest, 2)

    parts = [("Mortgage - interest", interest),
             ("Mortgage - principal", principal)]
    if abs(fee) >= 0.01:
        parts.append(("Mortgage - fees", fee))

    sign = -1.0 if amount < 0 else 1.0
    return [
        DerivedRow(f"{description}  [{category.split(' - ')[1]}]",
                   round(sign * value, 2), category)
        for category, value in parts
    ]
