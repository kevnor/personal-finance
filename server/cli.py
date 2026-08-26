"""Command-line entry points for building and checking the database."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from server.lib import categorise, derive, rules, store
from server.lib.ingest import dnb_xlsx

SOURCES = [
    ("Kontoutskrift.xlsx", "Bankkonto", "bank", dnb_xlsx.BANK),
    ("transaksjonsliste(1).xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
    ("transaksjonsliste.xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
]


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
    now = datetime.datetime.now().isoformat(timespec="seconds")

    inserted = skipped = derived = 0
    for filename, account, _kind, layout in SOURCES:
        path = Path(input_dir) / filename
        if not path.exists():
            continue
        rows = dnb_xlsx.read_statement(path, layout)
        batch = con.execute(
            "INSERT INTO import_batches (source_file, row_count, imported_at)"
            " VALUES (?, ?, ?)", (filename, len(rows), now)).lastrowid

        # Loan-term rows split into interest/principal/fee parts and never
        # pass through the normal categorise-then-insert path -- see
        # store.insert_derived_rows for why they must be kept out of it.
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

        loan_got, loan_dup, loan_made = store.insert_derived_rows(
            con, loan_rows, account_id, batch, derive.split_loan_term)
        inserted += loan_got
        skipped += loan_dup
        derived += loan_made

    count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    net = round(con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions").fetchone()[0], 2)
    con.close()
    return {"inserted": inserted, "skipped": skipped, "derived": derived,
            "net": net, "count": count}


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="server.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("import", "reconcile"):
        p = sub.add_parser(name)
        p.add_argument("--db", default=str(root / "data" / "transactions.db"))
        p.add_argument("--input", default=str(root / "input"))
        p.add_argument(
            "--expect-net", type=float, default=None,
            help="exit 1 if the resulting net does not equal this value"
                 " (no check by default)")

    args = parser.parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    result = build(args.db, args.input, root / "db" / "migrations")

    print(f"{result['count']} transactions, net {result['net']:.2f}")
    print(f"  inserted {result['inserted']}, already present {result['skipped']},"
          f" derived {result['derived']}")

    if args.expect_net is not None and result["net"] != args.expect_net:
        print(f"MISMATCH: expected net {args.expect_net:.2f}, got {result['net']:.2f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
