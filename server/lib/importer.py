"""Importing a batch of normalised rows into one account.

Extracted from `cli.build` when the HTTP API gained a statement upload. The
two callers must not drift: a preview shown by the API and the commit that
follows have to agree with each other *and* with what `python3 -m server.cli
import` would have done, or the same file produces different databases
depending on which door it came through.

The step that most needs sharing is the loan-term partition. Rows that split
into interest/principal/fee never pass through the normal categorise-then-
insert path -- see `store.insert_derived_rows` for why they must be kept out
of it -- and a second implementation of that rule is a second chance to get
it wrong.
"""
from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from server.lib.ingest import RawRow


@dataclass(frozen=True)
class ImportResult:
    inserted: int
    skipped: int
    derived: int


def new_batch(con: sqlite3.Connection, source_file: str,
              row_count: int) -> int:
    return con.execute(
        "INSERT INTO import_batches (source_file, row_count, imported_at)"
        " VALUES (?, ?, ?)",
        (source_file, row_count,
         datetime.datetime.now().isoformat(timespec="seconds"))).lastrowid


def partition(rows: Iterable[RawRow],
              splitter: Callable[[str, float], list]
              ) -> tuple[list[RawRow], list[RawRow]]:
    """Split rows into (normal, derivable).

    A row the splitter can itemise goes down the derived path instead of the
    normal one; everything else goes down the normal one.
    """
    normal: list[RawRow] = []
    derivable: list[RawRow] = []
    for row in rows:
        target = derivable if splitter(row.description, row.amount) else normal
        target.append(row)
    return normal, derivable


def import_rows(
    con: sqlite3.Connection,
    rows: list[RawRow],
    account_id: int,
    source_file: str,
    categoriser: Callable[[str], "object"],
    splitter: Callable[[str, float], list],
    counterparty: Callable[[str], str | None] | None = None,
) -> ImportResult:
    """Import one file's worth of rows. Additive and idempotent.

    Returns counts in *source rows* for inserted/skipped -- so the two sum to
    len(rows) -- and the number of derived rows written separately, since one
    source row can produce several.
    """
    # Imported here rather than at module scope: store imports nothing from
    # this module, and keeping the dependency one-way is what lets store stay
    # the lower layer.
    from server.lib import store

    batch = new_batch(con, source_file, len(rows))
    normal, derivable = partition(rows, splitter)

    inserted, skipped = store.upsert_transactions(
        con, normal, account_id, batch, categoriser, counterparty=counterparty)
    loan_inserted, loan_skipped, derived = store.insert_derived_rows(
        con, derivable, account_id, batch, splitter)

    return ImportResult(
        inserted=inserted + loan_inserted,
        skipped=skipped + loan_skipped,
        derived=derived)
