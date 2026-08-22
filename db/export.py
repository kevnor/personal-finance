#!/usr/bin/env python3
"""Export the database to portable CSV + SQL so it can be re-imported into the
real app once its code exists."""
import csv, os, sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "db", "transactions.db")
OUT = os.path.join(ROOT, "db")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

Q = """SELECT t.id, t.date, a.name AS account, t.description, t.amount,
              c.name AS category, c.kind AS category_kind,
              t.is_transfer, t.needs_review, t.counterparty,
              b.source_file, t.source_row
       FROM transactions t
       JOIN accounts a  ON a.id = t.account_id
       JOIN categories c ON c.id = t.category_id
       JOIN import_batches b ON b.id = t.batch_id
       ORDER BY t.date, t.id"""

rows = list(con.execute(Q))
cols = rows[0].keys()

def dump(path, data):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in data:
            w.writerow([r[c] for c in cols])
    return len(data)

n_all = dump(os.path.join(OUT, "transactions.csv"), rows)
n_rev = dump(os.path.join(OUT, "needs_review.csv"), [r for r in rows if r["needs_review"]])

with open(os.path.join(OUT, "import.sql"), "w", encoding="utf-8") as fh:
    for line in con.iterdump():
        fh.write(line + "\n")

print(f"transactions.csv  {n_all} rows")
print(f"needs_review.csv  {n_rev} rows")
print(f"import.sql        full dump")
con.close()
