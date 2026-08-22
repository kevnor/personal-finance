#!/usr/bin/env python3
"""Parse the Norwegian bank/credit-card statements in input/ and load them
into db/transactions.db, applying rule-based categorisation.

Self-contained: stdlib only (zipfile + ElementTree + sqlite3), no openpyxl.
Idempotent: re-running replaces the database from scratch.
"""
import datetime, os, re, sqlite3, sys, zipfile
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(ROOT, "input")
DB_PATH = os.path.join(ROOT, "db", "transactions.db")
SCHEMA = os.path.join(ROOT, "db", "schema.sql")
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXCEL_EPOCH = datetime.date(1899, 12, 30)

# ---------------------------------------------------------------- xlsx reader
def _col(ref):
    n = 0
    for ch in re.match(r"([A-Z]+)", ref).group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1

def read_sheet(path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    rows = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(f"{NS}row"):
        cells = {}
        for c in row.findall(f"{NS}c"):
            t, v, inline = c.get("t"), c.find(f"{NS}v"), c.find(f"{NS}is")
            if t == "inlineStr" and inline is not None:
                val = "".join(x.text or "" for x in inline.iter(f"{NS}t"))
            elif t == "s" and v is not None:
                val = shared[int(v.text)]
            elif v is not None:
                val = v.text
            else:
                continue
            cells[_col(c.get("r"))] = val
        if cells:
            rows.append([cells.get(i) or "" for i in range(max(cells) + 1)])
    return rows

def to_date(serial):
    return (EXCEL_EPOCH + datetime.timedelta(days=int(float(serial)))).isoformat()

def to_num(x):
    x = (x or "").strip()
    return float(x) if x else 0.0

# ------------------------------------------------------------------ categories
# (name, kind). Order here is only for readability.
CATEGORIES = [
    ("Salary", "income"), ("Employer reimbursement", "income"),
    ("Internal transfer", "transfer"), ("Credit card payment", "transfer"),
    ("Groceries", "expense"), ("Convenience & kiosk", "expense"),
    ("Cafe & bakery", "expense"), ("Restaurants & takeaway", "expense"),
    ("Bars & nightlife", "expense"), ("Public transport", "expense"),
    ("Taxi & ride-hailing", "expense"), ("Fuel & EV charging", "expense"),
    ("Clothing & shoes", "expense"), ("Sports & outdoor", "expense"),
    ("Home & furniture", "expense"), ("Flowers & plants", "expense"),
    ("Personal care", "expense"), ("Health - dental", "expense"),
    ("Health - pharmacy", "expense"), ("Health - doctor", "expense"),
    ("Utilities - electricity", "expense"), ("Insurance", "expense"),
    ("Gym & fitness", "expense"), ("Subscriptions", "expense"),
    ("Memberships", "expense"), ("Entertainment", "expense"),
    ("Accommodation", "expense"), ("Books", "expense"), ("Gifts", "expense"),
    ("Mortgage & loan", "expense"), ("Student loan", "expense"),
    ("Mortgage - interest", "expense"), ("Mortgage - fees", "expense"),
    ("Mortgage - principal", "transfer"), ("Employer loan repayment", "transfer"),
    ("Vipps P2P - unspecified", "expense"), ("Uncategorised", "expense"),
]

# (regex, category, needs_review). First match wins, so order matters:
# transfers and memo-bearing Vipps rows must be tested before generic merchants.
RULES = [
    # --- internal transfers (decision: excluded from income/spending) --------
    (r"^innbetaling$",                      "Credit card payment", 0),
    (r"til\s*:\s*99900011122",              "Credit card payment", 0),
    (r"overf.ring mellom egne konti",       "Internal transfer", 0),
    (r"ukespenger",                         "Internal transfer", 0),
    (r"mobil overf.ring",                   "Internal transfer", 0),
    # --- income --------------------------------------------------------------
    (r"^l.nn\b",                            "Salary", 0),
    (r"giro.*nordvest",                     "Employer reimbursement", 1),
    (r"nordvest as mobil betaling",         "Employer loan repayment", 0),
    # --- Vipps P2P, categorised by memo (decision: memo drives category) -----
    (r"stol fra jysk",                      "Home & furniture", 0),
    (r"\bspotify\b.*aalborg",               "Subscriptions", 0),
    (r"gave til mamma",                     "Gifts", 0),
    (r"humoretaten",                        "Entertainment", 0),
    (r"\bkino(tpp|ref|\b)",                  "Entertainment", 0),
    (r"\blading(tpp|ref|\b)",              "Fuel & EV charging", 0),
    (r"\bbok(tpp|ref)",                     "Books", 0),
    (r"\blatte(tpp|ref)",                   "Cafe & bakery", 0),
    (r"\bis(tpp|ref)",                      "Cafe & bakery", 0),
    (r"mat og snacks",                      "Groceries", 0),
    (r"\bmat(tpp|ref)",                     "Groceries", 0),
    # --- recurring bills & fixed costs ---------------------------------------
    (r"fjordkraft",                         "Utilities - electricity", 0),
    (r"gjensidige",                         "Insurance", 0),
    (r"\bsats\b",                           "Gym & fitness", 0),
    (r"baneleie|squash",                    "Sports & outdoor", 0),
    (r"spotify",                            "Subscriptions", 0),
    (r"morgenbladet",                       "Subscriptions", 0),
    (r"dnt-den norske|den norske t",        "Memberships", 0),
    (r"coop no medlem",                     "Memberships", 0),
    (r"statens l.nekasse",                  "Student loan", 0),
    (r"^l.n\b|avdrag",                      "Mortgage & loan", 1),
    # --- groceries -----------------------------------------------------------
    (r"\brema\b|rema 1000",                 "Groceries", 0),
    (r"\bmeny\b",                           "Groceries", 0),
    (r"\bkiwi\b",                           "Groceries", 0),
    (r"\bextra\b",                          "Groceries", 0),
    (r"\bspar\b",                           "Groceries", 0),
    (r"joker",                              "Groceries", 0),
    # --- eating out ----------------------------------------------------------
    (r"narvesen|7-eleven|deli de luca",     "Convenience & kiosk", 0),
    (r"proud mary|baker no|\bkb37\b|gr.d",  "Cafe & bakery", 0),
    (r"dominos|burger king|bastard burger", "Restaurants & takeaway", 0),
    (r"\bmcd\b|kebab|fly chicken|sumo",     "Restaurants & takeaway", 0),
    (r"veikroa|toke brygge",                "Restaurants & takeaway", 0),
    (r"kontroll_datter|^tilt\b|\btilt\s",   "Bars & nightlife", 0),
    (r"haugen",                             "Bars & nightlife", 0),
    # --- transport -----------------------------------------------------------
    (r"bolt\.eu",                           "Taxi & ride-hailing", 0),
    (r"vygruppen|vy app|^tog ga|\btog ga",  "Public transport", 0),
    (r"uno-x|mer norway",                   "Fuel & EV charging", 0),
    (r"ladestasjon",                         "Fuel & EV charging", 0),
    (r"circle k",                           "Fuel & EV charging", 0),
    # --- health --------------------------------------------------------------
    (r"tannklinikk",                        "Health - dental", 0),
    (r"apotek",                             "Health - pharmacy", 0),
    (r"\blege\b",                           "Health - doctor", 0),
    # --- shopping ------------------------------------------------------------
    (r"\bjysk\b|hoome|\bkid\b",             "Home & furniture", 0),
    (r"euro sko|boys storo|dios house",     "Clothing & shoes", 0),
    (r"volt 285",                           "Clothing & shoes", 0),
    (r"sport outlet",                       "Sports & outdoor", 0),
    (r"plantehallen|blomsterpiken",         "Flowers & plants", 0),
    (r"normal oslo|kondomeriet",            "Personal care", 0),
    # --- trips ---------------------------------------------------------------
    (r"leirvassbu|gjendebu",                "Accommodation", 0),
    # --- merchants confirmed by the account holder ---------------------------
    (r"all in one|hasle torg",              "Groceries", 0),
    # --- still unidentified: flagged so they surface in v_needs_review -------
    (r"maulund",                            "Uncategorised", 1),
    (r"ecom capital",                       "Uncategorised", 1),
]

VIPPS_RE = re.compile(r"vipps|tpp:|overf.ring", re.I)

# Reclassifications confirmed by the account holder that no rule could infer,
# because the memo describes the purchase and not its purpose.
# (date, amount, description fragment, category, note)
CORRECTIONS = [
    ("2026-07-28", -166.00, "Ingvild", "Gifts",
     "book bought as a present for mother; split three ways with siblings"),
    ("2026-07-28",   55.00, "Torkel", "Gifts",
     "Torkel' share of the present for mother"),
]

def apply_corrections(con, cat_id, kind_of):
    """Override rule-assigned categories with account-holder confirmations."""
    n = 0
    for date, amount, fragment, cat, note in CORRECTIONS:
        cur = con.execute(
            """UPDATE transactions SET category_id = ?, is_transfer = ?,
                      needs_review = 0, note = ?
               WHERE date = ? AND amount = ? AND description LIKE ?""",
            (cat_id[cat], 1 if kind_of[cat] == "transfer" else 0, note,
             date, amount, f"%{fragment}%"))
        if cur.rowcount == 0:
            print(f"  !! correction matched nothing: {date} {amount} {fragment}",
                  file=sys.stderr)
        n += cur.rowcount
    return n

# A loan term line itemises principal + interest inside its own description.
# Decision: interest and any fee are real expenses; principal is debt
# repayment, so it is booked as a transfer and left out of spending.
AVDRAG_RE = re.compile(r"avdrag\s+kr\s*([\d.]+,\d{2})", re.I)
RENTER_RE = re.compile(r"renter\s+kr\s*([\d.]+,\d{2})", re.I)

def _nok(s):
    return float(s.replace(".", "").replace(",", "."))

def split_loan_rows(con, cat_id, kind_of):
    """Expand each itemised loan term into interest / principal / fee rows."""
    n = 0
    targets = con.execute(
        """SELECT t.id, t.date, t.account_id, t.description, t.amount,
                  t.batch_id, t.source_row
           FROM transactions t JOIN categories c ON c.id = t.category_id
           WHERE c.name = 'Mortgage & loan'""").fetchall()
    for tid, date, acct, desc, amount, batch, srow in targets:
        a, r = AVDRAG_RE.search(desc), RENTER_RE.search(desc)
        if not (a and r):
            continue
        principal, interest = _nok(a.group(1)), _nok(r.group(1))
        fee = round(abs(amount) - principal - interest, 2)
        parts = [("Mortgage - interest", interest), ("Mortgage - principal", principal)]
        if abs(fee) >= 0.01:
            parts.append(("Mortgage - fees", fee))
        for cat, value in parts:
            con.execute(
                """INSERT INTO transactions
                   (date, account_id, description, amount, category_id,
                    is_transfer, needs_review, batch_id, source_row, is_derived, note)
                   VALUES (?,?,?,?,?,?,0,?,?,1,?)""",
                (date, acct, f"{desc}  [{cat.split(' - ')[1]}]", -round(value, 2),
                 cat_id[cat], 1 if kind_of[cat] == "transfer" else 0,
                 batch, srow, f"split from source row {srow}"))
        con.execute("DELETE FROM transactions WHERE id = ?", (tid,))
        n += 1
    return n

def extract_counterparty(desc):
    m = re.search(r"vipps\*([A-Za-zÆØÅæøå' .-]+?)(?:,|$)", desc, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"vipps:([A-Za-zÆØÅæøå' .-]+)", desc, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\d{6,}\s+([A-ZÆØÅ][A-Za-zÆØÅæøå.-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå.-]+){1,3})", desc)
    if m:
        return m.group(1).strip()
    return None

def categorise(desc, amount):
    low = desc.lower()
    for pattern, cat, review in RULES:
        if re.search(pattern, low):
            return cat, review
    # Unmatched Vipps / bank transfer with no memo -> needs a human decision
    if VIPPS_RE.search(low):
        return "Vipps P2P - unspecified", 1
    return "Uncategorised", 1

# ---------------------------------------------------------------------- import
SOURCES = [
    # (filename, account, kind, date_col, desc_col, in_col, out_col)
    ("Kontoutskrift.xlsx",         "Bankkonto",   "bank",        0, 1, 4, 3),
    ("transaksjonsliste(1).xlsx",  "Kredittkort", "credit_card", 0, 1, 4, 5),
    ("transaksjonsliste.xlsx",     "Kredittkort", "credit_card", 0, 1, 4, 5),
]
SKIP_RE = re.compile(r"skyldig bel.p fra forrige faktura", re.I)  # opening balance

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.executescript(open(SCHEMA, encoding="utf-8").read())

    cat_id = {}
    for name, kind in CATEGORIES:
        cur = con.execute("INSERT INTO categories (name, kind) VALUES (?, ?)", (name, kind))
        cat_id[name] = cur.lastrowid
    kind_of = dict(CATEGORIES)

    acct_id = {}
    for _, acct, kind, *_ in SOURCES:
        if acct not in acct_id:
            cur = con.execute("INSERT INTO accounts (name, kind) VALUES (?, ?)", (acct, kind))
            acct_id[acct] = cur.lastrowid

    now = datetime.datetime.now().isoformat(timespec="seconds")
    inserted = skipped = dupes = 0

    for fname, acct, _kind, dc, xc, ic, oc in SOURCES:
        path = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(path):
            print(f"  !! missing {fname}", file=sys.stderr)
            continue
        rows = read_sheet(path)[1:]          # drop header
        batch = con.execute(
            "INSERT INTO import_batches (source_file, row_count, imported_at) VALUES (?,?,?)",
            (fname, len(rows), now)).lastrowid
        n_skip = 0
        for lineno, r in enumerate(rows, start=2):
            r = r + [""] * (max(dc, xc, ic, oc) + 1 - len(r))
            desc = (r[xc] or "").strip()
            if not desc or not (r[dc] or "").strip():
                n_skip += 1; continue
            if SKIP_RE.search(desc):         # invoice carry-over, not a transaction
                n_skip += 1; continue
            amount = round(to_num(r[ic]) - to_num(r[oc]), 2)
            cat, review = categorise(desc, amount)
            try:
                con.execute(
                    """INSERT INTO transactions
                       (date, account_id, description, amount, category_id,
                        is_transfer, needs_review, counterparty, batch_id, source_row)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (to_date(r[dc]), acct_id[acct], desc, amount, cat_id[cat],
                     1 if kind_of[cat] == "transfer" else 0, review,
                     extract_counterparty(desc), batch, lineno))
                inserted += 1
            except sqlite3.IntegrityError:
                dupes += 1
        con.execute("UPDATE import_batches SET skipped_rows=? WHERE id=?", (n_skip, batch))
        skipped += n_skip

    n_split = split_loan_rows(con, cat_id, kind_of)
    n_fixed = apply_corrections(con, cat_id, kind_of)
    con.commit()
    if n_split:
        print(f"split {n_split} loan row(s) into interest / principal / fee")
    if n_fixed:
        print(f"applied {n_fixed} account-holder correction(s)")
    print(f"inserted {inserted} transactions "
          f"({skipped} opening-balance/blank rows skipped, {dupes} exact duplicates collapsed)")
    return con

if __name__ == "__main__":
    main().close()
