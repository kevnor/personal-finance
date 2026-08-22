# Transaction database

Self-contained SQLite database built from the statements in `../input/`.
Standalone by necessity — the app in `client/` and `server/` has no source
files, so this does not depend on it. `import.sql` / `transactions.csv` are
here so the data can be moved into the real app once its code exists.

## Rebuild

```bash
python3 db/import_transactions.py && python3 db/export.py
```

Stdlib only (no openpyxl, no npm). Destructive and idempotent: it deletes
`transactions.db` and rebuilds from the source spreadsheets every run, so
categorisation rules are edited in `import_transactions.py`, never by hand
in the database.

## Files

| File | What it is |
|---|---|
| `schema.sql` | Tables + the `v_spending` / `v_income` / `v_needs_review` views |
| `import_transactions.py` | xlsx parser, categorisation rules, loan splitter |
| `export.py` | Writes the CSV and SQL exports |
| `transactions.db` | The database — 181 rows |
| `transactions.csv` | Flat categorised export |
| `needs_review.csv` | The 29 rows still needing a human decision (26 are memo-less Vipps) |
| `import.sql` | Full `iterdump()`, for replaying into another database |

## Sources

| File | Account | Period | Rows |
|---|---|---|---|
| `Kontoutskrift.xlsx` | Bankkonto | 2026-06-30 → 07-30 | 123 |
| `transaksjonsliste(1).xlsx` | Kredittkort | 2026-06-10 → 07-08 | 44 |
| `transaksjonsliste.xlsx` | Kredittkort | 2026-07-20 → 08-09 | 14 |

Dates in the source are Excel serials (epoch 1899-12-30) and are converted to
ISO on import. Two `Skyldig beløp fra forrige faktura` rows are invoice
carry-over balances, not transactions, and are skipped.

## Conventions

`amount` is signed: positive is money in, negative is money out. Rows with
`is_transfer = 1` are internal movements and are excluded from both the
spending and income views. `needs_review = 1` marks a row whose category is a
guess or unknown.

Because one source row can legitimately repeat (two coffees at the same shop
on the same day, paid separately) row identity is
`(batch_id, source_row, description, amount)` — not date+amount, which would
silently discard real spending.

## Categorisation decisions

1. **Credit-card payments are transfers.** The `Innbetaling` rows on the card
   and the matching bank transfer (4 982,80, and `til : 99900011122`) are
   tagged `Credit card payment` and excluded from totals. The card's own
   purchase lines carry the real spending, so counting both would
   double-count roughly 32 000 kr.
2. **`Ukespenger` and `Mobil Overføring` are own-account transfers**, along
   with the explicit `Overføring Mellom Egne Konti`. Excluded from income.
3. **Vipps person-to-person is categorised by its memo** — `Mat` → Groceries,
   `Kino` → Entertainment, `Lading` → Fuel & EV charging, `Bok` → Books,
   `Latte`/`Is` → Cafe & bakery, `Stol Fra Jysk` → Home & furniture. Incoming
   ones net against that category, so the 1 800 kr Jysk chair reimbursed by
   Sindre cancels the 1 800 kr purchase. The 26 memo-less rows stay in
   `Vipps P2P - unspecified`, flagged.
4. **Loan terms are split.** `Avdrag`/`Renter` are parsed out of the
   description: interest and the term fee are expenses, principal is a
   transfer (debt repayment, not consumption). The three derived rows carry
   `is_derived = 1` and sum back to the original charge.
5. **The 800 kr to Nordvest Teknikk AS marked "Dividend" is a loan repayment** to the
   employer, confirmed by the account holder. Booked as
   `Employer loan repayment` (transfer) on the same reasoning as mortgage
   principal, despite what the statement text says.
6. **Merchants identified by the account holder:** VOLT 285 → Clothing &
   shoes; All In One AS and Hasle Torg → Groceries. `MAULUND A/S` (298) and
   `Ecom Capital AS` (210) remain unidentified and stay flagged.

7. **A memo says what was bought, not why.** The 166 kr Vipps payment to
   Ingvild on 2026-07-28 carries the memo `Bok`, but the book was a present for
   the account holder's mother, split three ways with Sindre and Torkel (166 / 3
   = 55,33 each). Rules cannot infer purpose from a memo, so this and Torkel'
   55 kr share are reassigned via the `CORRECTIONS` list in
   `import_transactions.py`, which overrides rule output for rows the account
   holder has confirmed. `Gifts` therefore nets to 56,00 — the account
   holder's own share — and `Books` is now empty.

Add future one-off reclassifications to `CORRECTIONS` rather than editing the
database, so they survive a rebuild. Each entry warns on stderr if it stops
matching any row.
