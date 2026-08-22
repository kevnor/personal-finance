"""Content-based transaction identity.

Statement exports carry no stable transaction id, so identity is derived
from content. Row position is deliberately excluded: a re-export may order
rows differently, and position-based identity would duplicate the lot.

Because the same merchant, day and amount can occur twice for real (two
coffees paid separately), identity is the fingerprint *plus* an occurrence
index. Keying on the fingerprint alone silently discards real spending.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from server.lib.ingest.dnb_xlsx import RawRow


def fingerprint(account: str, date: str, description: str,
                amount: float) -> str:
    payload = "\x1f".join(
        (account, date, description.strip(), f"{amount:.2f}"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def with_identity(rows: list[RawRow],
                  account: str) -> list[tuple[RawRow, str, int]]:
    seen: dict[str, int] = defaultdict(int)
    out: list[tuple[RawRow, str, int]] = []
    for row in rows:
        fp = fingerprint(account, row.date, row.description, row.amount)
        seen[fp] += 1
        out.append((row, fp, seen[fp]))
    return out
