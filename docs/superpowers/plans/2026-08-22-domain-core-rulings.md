# Domain core — decisions taken during execution

Twenty-four rulings made while executing
[2026-08-22-domain-core.md](2026-08-22-domain-core.md). Each amended the plan
mid-flight, so **the plan text alone is not the specification** — the plan as
amended by these is. Recorded because the reasoning is not recoverable from the
commit history, and several items below must be carried into the next plan.

Format: decision — why — what it costs if wrong.

## Pre-flight (before any code)

**1. Cancelled migration `004_seed_treatments.sql`.** A migration that
`UPDATE`s `categories` by name is a no-op: categories are inserted by
application code *after* migrations run, and `migrate` is name-recorded so
re-calling never re-applies. Treatments moved to `categorise.TREATMENTS`,
applied by `store.seed_reference_data`. Verified empirically before execution.
*Cost:* treatments live in Python, so a hand-edited database is not
self-describing — recoverable by re-running the seeder. **This is why the
migration numbering skips 004.**

**2. `store.seed_reference_data` takes its data as explicit parameters.**
Tasks 6, 9 and 10 all seed identically, and `store.py` is persistence with no
business knowing category semantics — it also cannot import `categorise`,
which does not exist until Task 3. *Cost:* callers pass two constants.

## During the task loop

**3. Restored the absent-columns test via a 001-only migrations subset** rather
than deleting the guard as dead code. The guard looks unreachable because
seeding always follows a full migrate — but `migrate()` could leave migrations
*partially* applied, producing exactly that schema. *Cost:* one
contrived-looking test.

**4. Asserted the full `Verdict` across all 176 golden cases.** The suite
asserted only `.category`, so any `needs_review` flag flip passed — and that
flag drives the review queue, the only mechanism surfacing uncertain rows.
*Cost:* none identified; the stronger assertion already passed.

**5. Pulled two cheap coverage gaps into the same round** (TREATMENTS value
validation, the uncovered `Books` rule) rather than a later pass. *Cost:* a
slightly larger fix round.

**6. Kept the no-op `"Credit card payment"` TREATMENTS entry** despite it
writing the schema defaults back and contradicting my own "only deviating
categories" wording. The comment above it records the anti-double-counting
decision; silence would lose that. *Cost:* one redundant dict entry.

**7. Index predicate `WHERE is_derived = 0 AND fingerprint <> ''`.** Migration
002 backfills `fingerprint = ''`, so without this every legacy row collapsed
onto one key and 003 could never apply to a non-empty database. *Cost:*
unfingerprinted rows get no database-level uniqueness.

**8. Fingerprint hashes `str(account_id)`; `account_name` dropped from
`upsert_transactions`.** Hashing a mutable display name meant renaming an
account re-duplicated an entire statement (reproduced: 86 rows from one
statement). *Cost:* fingerprints are comparable only within one database —
all the index needs.

**9. Added the partial-reimport and stored-column tests in the same round**, as
both harden exactly what changed. *Cost:* larger round.

**10. Trailing averages filtered to months at or before the target month.**
They averaged over *all* complete months, so a future month polluted a past
month's estimate. Rejected a bounded window (e.g. last three months) as a
design decision beyond the spec. *Cost:* estimates drift as older months are
backfilled.

**11. `ORDER BY effective_from DESC, id DESC`** so a same-day config
correction wins its tie instead of silently returning the stale row. *Cost:*
none identified.

**12. Required DB-backed tests for `figures()` and `_variable_spent()`.** The
committed suite tested only the pure-arithmetic half, leaving the
treatment/transfer filtering — every requirement deciding whether the number
is right — unverified. *Cost:* one more test module.

**13. `mark_reimbursable` made idempotent, with a UNIQUE index on
`reimbursements(transaction_id)`.** A retry produced two debt rows, so
"owed" reported double. Defence in depth on money: the app check keeps the API
sane, the constraint makes the bug impossible. One transaction = one
reimbursement for v1. *Cost:* a genuinely split reimbursement needs a schema
change later.

**14. `mark_reimbursable` no longer clears `needs_review`.** Recording a debt
says nothing about whether the category is right; an uncategorised row was
silently leaving the review queue. *Cost:* a row flagged for an unrelated
reason stays flagged until someone resolves the real question.

**15. `learned_map` orders by `length(pattern) DESC`.** With no ordering, which
of two matching taught patterns won was whatever SQLite returned — defeating a
feature whose promise is "teach it once and it stays taught". *Cost:* a broad
rule cannot beat a narrow one.

**16. Derived-row identity moved into `store.py`.** It was duplicated in
`cli.py`, and that copy was the one with no database constraint behind it, so
a future identity change landing in `store.py` alone would silently duplicate.
*Cost:* `store.py` grows by one function.

**17. Replaced the hardcoded expected net with an optional `--expect-net`.**
`reconcile` exited 1 the first time a genuinely new statement was imported —
hard failure for the normal outcome. The invariant stays enforced in the tests.
*Cost:* `reconcile` self-checks only when asked.

**18. Pulled in the direct split-path test and the `skipped` counter fix**, as
that logic had already regressed once. *Cost:* larger round.

## Whole-branch review

**19. One consolidated fix wave**, not one fixer per finding. *Cost:* a single
long-running agent — it was in fact killed by a session limit after its 14th
commit, though nothing was lost.

**20. Restored `v_spending` / `v_income` / `v_needs_review` in migration 006**
rather than amending the spec to retire them. They were dropped with
`schema.sql`, the spec says they are unchanged, and two files still referenced
them. *Cost:* three views nothing reads yet.

**21. The legacy-database fix is a loud refusal, not a silent backfill.**
Importing into a legacy-migrated database produced 362 rows at net 28168.48 —
*stably* wrong across runs, which is the worst failure mode here. The guard
runs before `migrate()`, so a refusal leaves the artifact's schema untouched.
`db/transactions.db` was **moved**, not deleted, to
`data/legacy-2026-08-22.db`. *Cost:* a legacy database needs an explicit
backfill before it can be imported.

**22. All remaining minors stay deferred**, accepting the reviewer's
"can stand" triage.

**23. Accepted three residuals rather than opening a second fix wave.** The
process allows no second wave; residuals surface to the human:

- The **cold-start** `expected_committed` fallback still sums the target month,
  so the pool can move mid-month in that regime (22650.07 → 19242.81
  reproduced). No live number moves — the real data is in the averaged regime
  from 2026-07 on. *Cost:* a first-run user on a partial month sees the
  envelope shift when a debt instalment posts.
- `_variable_spent`'s `is_transfer = 0` and the views' transfer filters are no
  longer killable by any test: adding `c.kind = 'expense'` made them
  co-extensive for pipeline-written rows. Behaviour is correct, defence-in-depth
  coverage was lost. *Cost:* a future writer setting `is_transfer`
  independently of category kind could break the invariant unnoticed.
- **Carry into the next plan:** `origin` defaults to `'import'` in migration
  002, so a manual-entry path will trip the legacy guard's `LegacyDataError`
  unless it sets `origin = 'manual'` explicitly.

**24. The two unmandated commits are justified completions.** `ed607a2` moves
the guard ahead of `migrate()`, without which Ruling 21 fails its own purpose.
`bc8bdba` backfills `counterparty`, without which that finding's symptom stays
permanently true on the existing database, since re-import skips every row.

## Two mistakes of mine the reviews caught

- I recorded the root cause of the **salary-netting bug** as a Task 2
  "minor (deferred) … spec-level oddity". It was not an oddity; it was the
  cause. `budget_treatment` has no income-appropriate value, so income
  categories inherited `variable` and the salary counted as *negative*
  spending — payday week reported −39 254,82 instead of 1 858,85.
- I told an implementer there were **five migrations**. There were four, the
  gap at 004 being Ruling 1's own consequence.
