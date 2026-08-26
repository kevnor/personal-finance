"""Command-line entry points for building and checking the database."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from server import corrections
from server.lib import budget, categorise, derive, rules, store
from server.lib.ingest import dnb_xlsx

SOURCES = [
    ("Kontoutskrift.xlsx", "Bankkonto", "bank", dnb_xlsx.BANK),
    ("transaksjonsliste(1).xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
    ("transaksjonsliste.xlsx", "Kredittkort", "credit_card", dnb_xlsx.CARD),
]


def build(db_path, input_dir, migrations_dir) -> dict:
    if not Path(input_dir).is_dir():
        # Individual statements are legitimately absent -- only some of the
        # three may have been dropped in. A missing directory is different:
        # it is a mistyped path, and reporting "0 transactions, net 0.00" for
        # it reads as "nothing new to import".
        raise FileNotFoundError(f"input directory does not exist: {input_dir}")

    con = store.connect(db_path)
    store.migrate(con, migrations_dir)
    store.require_fingerprinted_imports(con)
    store.seed_reference_data(
        con,
        categorise.CATEGORIES,
        categorise.TREATMENTS,
        [(account, kind) for _, account, kind, _ in SOURCES])
    budget.seed_default_config(con)

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
            lambda d: categorise.categorise(d, learned=learned),
            counterparty=categorise.extract_counterparty)
        inserted += got
        skipped += dup

        loan_got, loan_dup, loan_made = store.insert_derived_rows(
            con, loan_rows, account_id, batch, derive.split_loan_term)
        inserted += loan_got
        skipped += loan_dup
        derived += loan_made

    # Applied on every import, not just once by hand: the two corrections
    # change no amount, so the 181/14084.24 reconciliation cannot notice them
    # missing. They are content-keyed and idempotent, so a run that has
    # nothing to fix does nothing.
    fixes = corrections.apply(con)

    count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    net = round(con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions").fetchone()[0], 2)
    con.close()
    return {"inserted": inserted, "skipped": skipped, "derived": derived,
            "net": net, "count": count, "corrections": fixes}


def reconcile(db_path) -> dict:
    """Report the dataset without touching it.

    A command promising reconciliation must not mutate. It previously shared
    every line of `import` -- `args.command` was never read once Ruling 17
    removed the hardcoded net -- so `reconcile` against a fresh database
    inserted 179 rows and exited 0. The connection is opened mode=ro so the
    promise is enforced by SQLite rather than by this function's good
    intentions, and no migration runs: reporting must not change a schema
    either.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"no database at {path}. `reconcile` reports an existing database"
            " and never creates one -- run `import` first.")

    con = store.connect(path, read_only=True)
    count = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    net = round(con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions").fetchone()[0], 2)
    flagged = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE needs_review = 1").fetchone()[0]
    con.close()
    return {"count": count, "net": net, "needs_review": flagged}


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(prog="server.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--db", default=str(root / "data" / "transactions.db"))
        p.add_argument(
            "--expect-net", type=float, default=None,
            help="exit 1 if the resulting net does not equal this value"
                 " (no check by default)")
        return p

    importer = add_common(sub.add_parser(
        "import", help="read the statements in --input and insert new rows"))
    importer.add_argument("--input", default=str(root / "input"))
    add_common(sub.add_parser(
        "reconcile", help="report an existing database; writes nothing"))

    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
            result = build(args.db, args.input, root / "db" / "migrations")
            print(f"{result['count']} transactions, net {result['net']:.2f}")
            print(f"  inserted {result['inserted']},"
                  f" already present {result['skipped']},"
                  f" derived {result['derived']}")
            fixes = result["corrections"]
            print(f"  corrections: {fixes['applied']} applied,"
                  f" {fixes['already']} already in place,"
                  f" {fixes['missing']} rows not present")
        else:
            result = reconcile(args.db)
            print(f"{result['count']} transactions, net {result['net']:.2f}")
            print(f"  {result['needs_review']} need review;"
                  f" read-only, nothing written")
    except (FileNotFoundError, store.LegacyDataError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.expect_net is not None and result["net"] != args.expect_net:
        print(f"MISMATCH: expected net {args.expect_net:.2f}, got {result['net']:.2f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
