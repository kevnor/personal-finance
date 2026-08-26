# Transaction database

SQLite database built from the statements in `../input/` by the pipeline in
`server/`. `server/cli.py` wires together the ingest, categorisation, and
derivation modules under `server/lib/`; this file documents the data itself —
where it comes from, what the columns mean, and why the categorisation rules
are shaped the way they are.

## Rebuild

```bash
python3 -m server.cli import
```

Additive and idempotent — safe to re-run, and re-importing an overlapping
statement period is a no-op. Categorisation rules live in
`server/lib/categorise.py`; per-transaction corrections are persisted in the
`merchant_rules` table via `server/lib/rules.py`, not in code.

## Files

| Path | What it is |
|---|---|
| `db/migrations/` | Numbered SQL migrations, applied in filename order |
| `server/lib/` | Ingest, categorisation, budget engine |
| `server/cli.py` | `import` (writes) and `reconcile` (read-only) commands |
| `data/transactions.db` | The live database — the only one any code writes (gitignored) |
| `data/legacy-2026-08-22.db` | The original hand-built database (gitignored) — see below |

### `data/legacy-2026-08-22.db`

The database produced by the pre-app standalone script, kept only as a
reference: it is the sole record of the 48 `counterparty` values the script
extracted and of the hand corrections applied during the 2026-08-22 session.
**No current code reads or writes it, and it must not be copied over
`data/transactions.db`.** Its 181 rows predate content-fingerprint identity
(migration 002 backfills `fingerprint = ''`, and 003's unique index
deliberately excludes those rows), so importing into it would insert every
statement row a second time — 362 rows, net 28 168,48, and stably wrong
across repeated runs. `import` refuses to run against such a database
(`store.require_fingerprinted_imports`) rather than producing that number
quietly.

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
on the same day, paid separately) row identity is a content fingerprint —
a hash of account, date, description and amount — plus an occurrence index
counting repeats of that same fingerprint within one import. Position in the
sheet is deliberately excluded, since a re-export can reorder rows; identity
by date+amount alone would silently discard real repeated spending. See
`server/lib/ingest/fingerprint.py`.

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
   55 kr share are reassigned to `Gifts` by hand (see below). `Gifts`
   therefore nets to 56,00 — the account holder's own share — and `Books` is
   now empty.
8. **The Hoome (phone) charge is reimbursable, not an expense.** It is paid
   for by the account holder's employer, Nordvest Teknikk AS, so it is recorded via
   `rules.mark_reimbursable` as a debt owed rather than recategorised —
   marking a debt says nothing about whether the category itself is right.

One-off corrections that a rule cannot express — because they depend on
context no description carries, like decisions 7 and 8 above — are applied
directly against the built database rather than by editing
`server/lib/categorise.py`. Decision 8 uses `rules.mark_reimbursable`, which
records a debt against a specific transaction id. Decision 7 targets two
specific transaction ids directly with `UPDATE`, since it reassigns a
category by hand-identified context rather than by a pattern that should
apply to any future matching row — a merchant pattern (`rules.teach`) would
be the wrong tool here, since `Bok` genuinely does mean Books most of the
time. Either way the correction is persisted state, not code, so it survives
a rebuild without needing to be re-run.
