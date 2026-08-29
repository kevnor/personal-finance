"""Statement upload: preview first, then commit.

The spec is explicit that preview before write is required -- "a silent
half-duplicating import is painful to unpick" -- so this is deliberately two
calls rather than one. Both parse the file the same way and run the same
identity computation, so what the preview promises is what the commit does.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile,
                     status)

from server.deps import db, db_ro, household
from server.lib import (categorise, derive, importer, local, rules,
                        store)
from server.lib.ingest import dnb_xlsx
from server.schemas import ImportOut, PreviewOut, PreviewRow

router = APIRouter(prefix="/api/imports", tags=["imports"])

# 422. Spelled as a literal because starlette renamed the constant
# (HTTP_422_UNPROCESSABLE_ENTITY -> ..._CONTENT) and deprecated the old
# name; the number is the part that is actually stable.
UNPROCESSABLE = 422
TOO_LARGE = 413

# A DNB statement export is a few tens of kilobytes. The cap is here because
# the file is read into memory to be parsed, so an unbounded upload is an
# unbounded allocation -- and this app has no reason to accept one.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Which spreadsheet layout each kind of account exports. The bank and card
# statements disagree about which column holds money out (3 vs 5), and the
# reader cannot tell them apart -- read under the wrong layout a file keeps
# its credits and silently reads every debit as 0,00. So the layout comes
# from the account the caller names, exactly as `cli.SOURCES` pairs each
# filename with one.
LAYOUTS = {"bank": dnb_xlsx.BANK, "credit_card": dnb_xlsx.CARD}


def _account(con: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = con.execute("SELECT id, name, kind FROM accounts WHERE name = ?",
                      (name,)).fetchone()
    if row is None:
        known = [r["name"] for r in con.execute(
            "SELECT name FROM accounts ORDER BY name")]
        raise HTTPException(
            UNPROCESSABLE,
            f"unknown account {name!r}; known accounts: {known}")
    if row["kind"] not in LAYOUTS:
        raise HTTPException(
            UNPROCESSABLE,
            f"no statement layout for account kind {row['kind']!r}")
    return row


def _read_rows(upload: UploadFile, layout) -> list:
    """Parse an uploaded statement into normalised rows.

    Written to a temporary file because the reader takes a path: it opens the
    .xlsx as a zip archive, and handing it a path keeps one reader working
    for both the CLI (a file on disk) and the API (an upload) rather than
    growing a second code path for streams.

    Reads `upload.file` synchronously rather than awaiting `upload.read()`,
    which is what keeps these handlers `def` rather than `async def`. See the
    note on the route handlers below: it is a correctness requirement here,
    not a style choice.
    """
    payload = upload.file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            TOO_LARGE,
            f"file is larger than {MAX_UPLOAD_BYTES} bytes")
    if not payload:
        raise HTTPException(UNPROCESSABLE,
                            "uploaded file is empty")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / (upload.filename or "statement.xlsx")
        path.write_bytes(payload)
        try:
            return dnb_xlsx.read_statement(path, layout)
        except Exception as exc:
            # A corrupt zip, a sheet that is not there, a column that is not
            # a date: all mean the same thing to the caller -- this is not a
            # statement this reader understands -- and none of them is a bug
            # in the server worth a 500.
            raise HTTPException(
                UNPROCESSABLE,
                f"could not read {upload.filename!r} as a DNB statement:"
                f" {exc}")


# Both handlers are deliberately `def`, not `async def`.
#
# FastAPI runs a sync handler and its sync dependencies on the same threadpool
# worker; an async handler runs on the event loop while its sync dependencies
# still run in the threadpool. sqlite3 connections are bound to the thread
# that created them, so an async handler here raises "SQLite objects created
# in a thread can only be used in that same thread" the moment it touches the
# connection -- reliably, on every request. There is nothing to await in
# either handler (parsing and SQLite are both blocking), so sync is also the
# honest description of what they do.


@router.post("/preview", response_model=PreviewOut)
def preview(file: UploadFile = File(...), account: str = Form(...),
            con: sqlite3.Connection = Depends(db_ro),
            home: local.LocalData = Depends(household)):
    """Say what committing this file would do, without writing anything.

    Read-only at the connection level, so the promise is enforced by SQLite
    rather than by this function's good intentions.
    """
    row = _account(con, account)
    rows = _read_rows(file, LAYOUTS[row["kind"]])
    learned = rules.learned_map(con)

    classified = store.classify_rows(
        con, rows, row["id"],
        lambda description: categorise.categorise(
            description, learned=learned, extra_rules=home.rules))

    return PreviewOut(
        account=row["name"],
        total=len(classified),
        new=sum(1 for r in classified if r["status"] == "new"),
        existing=sum(1 for r in classified if r["status"] == "existing"),
        needs_review=sum(1 for r in classified
                         if r["status"] == "new" and r["needs_review"]),
        rows=[PreviewRow(**r) for r in classified])


@router.post("", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
def commit(file: UploadFile = File(...), account: str = Form(...),
           con: sqlite3.Connection = Depends(db),
           home: local.LocalData = Depends(household)):
    """Import the file. Additive and idempotent, like every other ingest path.

    Re-uploading a statement already imported inserts nothing and reports it
    as skipped, so a user who is unsure whether they already did it can just
    do it again.
    """
    row = _account(con, account)
    rows = _read_rows(file, LAYOUTS[row["kind"]])
    learned = rules.learned_map(con)

    result = importer.import_rows(
        con, rows,
        account_id=row["id"],
        source_file=file.filename or "upload.xlsx",
        categoriser=lambda description: categorise.categorise(
            description, learned=learned, extra_rules=home.rules),
        splitter=derive.split_loan_term,
        counterparty=categorise.extract_counterparty)

    return ImportOut(account=row["name"], inserted=result.inserted,
                     skipped=result.skipped, derived=result.derived)
