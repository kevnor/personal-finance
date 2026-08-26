"""Command-line entry points for building and checking the database."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from server.lib import categorise, derive, rules, store
from server.lib.ingest import dnb_xlsx
from server.lib.ingest.fingerprint import with_identity

SOURCES = [
    ("Kontoutskrift.xlsx", "Bankkonto", "bank", dnb_xlsx.BANK),
    ("transaksjonsliste(1).xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
    ("transaksjonsliste.xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
]


def _insert_loan_splits(con, rows, account_id, batch_id, ids, kinds) -> int:
    """Insert derived interest/principal/fee rows for splittable loan rows.

    Loan rows never pass through the normal categorise-then-insert path:
    upsert_transactions' identity check only matches undeleted is_derived=0
    rows, so inserting a loan row plainly and then deleting it in favour of
    its derived parts (as an earlier design did) makes that row invisible
    to the identity check on the next run -- it gets reinserted and
    resplit every time, silently doubling the derived totals. Splitting
    before anything is written keeps a single, stable identity: the derived
    rows themselves carry the source fingerprint, and a repeat run checks
    for an existing is_derived=1 row with that fingerprint before inserting
    again.
    """
    made = 0
    for row, fp, occurrence in with_identity(rows, str(account_id)):
        parts = derive.split_loan_term(row.description, row.amount)
        if not parts:
            continue
        exists = con.execute(
            "SELECT 1 FROM transactions"
            " WHERE account_id = ? AND fingerprint = ? AND occurrence = ?"
            "   AND is_derived = 1",
            (account_id, fp, occurrence)).fetchone()
        if exists:
            continue
        for part in parts:
            con.execute(
                "INSERT INTO transactions (date, account_id, description,"
                " amount, category_id, is_transfer, needs_review, batch_id,"
                " source_row, fingerprint, occurrence, is_derived, origin, note)"
                " VALUES (?,?,?,?,?,?,0,?,?,?,?,1,'derived',?)",
                (row.date, account_id, part.description, part.amount,
                 ids[part.category],
                 1 if kinds[part.category] == "transfer" else 0,
                 batch_id, row.source_row, fp, occurrence,
                 f"split from source row {row.source_row}"))
            made += 1
    con.commit()
    return made


def build(db_path, input_dir, migrations_dir) -> dict:
    con = store.connect(db_path)
    store.migrate(con, migrations_dir)
    store.seed_reference_data(
        con,
        categorise.CATEGORIES,
        categorise.TREATMENTS,
        [(account, kind) for _, account, kind, _ in SOURCES])

    learned = rules.learned_map(con)
    accounts = {r["name"]: r["id"]
                for r in con.execute("SELECT id, name FROM accounts")}
    ids = {r["name"]: r["id"]
           for r in con.execute("SELECT id, name FROM categories")}
    kinds = {r["name"]: r["kind"]
             for r in con.execute("SELECT name, kind FROM categories")}
    now = datetime.datetime.now().isoformat(timespec="seconds")

    inserted = skipped = made = 0
    for filename, account, _kind, layout in SOURCES:
        path = Path(input_dir) / filename
        if not path.exists():
            continue
        rows = dnb_xlsx.read_statement(path, layout)
        batch = con.execute(
            "INSERT INTO import_batches (source_file, row_count, imported_at)"
            " VALUES (?, ?, ?)", (filename, len(rows), now)).lastrowid

        normal_rows, loan_rows = [], []
        for row in rows:
            target = loan_rows if derive.split_loan_term(
                row.description, row.amount) else normal_rows
            target.append(row)

        account_id = accounts[account]
        got, dup = store.upsert_transactions(
            con, normal_rows, account_id, batch,
            lambda d: categorise.categorise(d, learned=learned))
        inserted += got
        skipped += dup

        made += _insert_loan_splits(con, loan_rows, account_id, batch, ids, kinds)

    count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    net = round(con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions").fetchone()[0], 2)
    con.close()
    return {"inserted": inserted, "skipped": skipped, "derived": made,
            "net": net, "count": count}


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="server.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("import", "reconcile"):
        p = sub.add_parser(name)
        p.add_argument("--db", default=str(root / "data" / "transactions.db"))
        p.add_argument("--input", default=str(root / "input"))

    args = parser.parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    result = build(args.db, args.input, root / "db" / "migrations")

    print(f"{result['count']} transactions, net {result['net']:.2f}")
    print(f"  inserted {result['inserted']}, already present {result['skipped']},"
          f" derived {result['derived']}")

    if args.command == "reconcile" and result["net"] != 14084.24:
        print(f"MISMATCH: expected net 14084.24, got {result['net']:.2f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
