-- Personal finance schema (SQLite)
-- Sign convention: amount > 0 = money in, amount < 0 = money out.
-- Rows with is_transfer = 1 are internal movements and must be excluded
-- from income/spending aggregates (see the v_spending / v_income views).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    kind  TEXT NOT NULL CHECK (kind IN ('bank', 'credit_card'))
);

CREATE TABLE IF NOT EXISTS categories (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL UNIQUE,
    kind   TEXT NOT NULL CHECK (kind IN ('expense', 'income', 'transfer')),
    parent TEXT
);

CREATE TABLE IF NOT EXISTS import_batches (
    id           INTEGER PRIMARY KEY,
    source_file  TEXT NOT NULL,
    row_count    INTEGER NOT NULL,
    skipped_rows INTEGER NOT NULL DEFAULT 0,
    imported_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY,
    date         TEXT    NOT NULL,              -- ISO yyyy-mm-dd
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    description  TEXT    NOT NULL,              -- verbatim from statement
    amount       REAL    NOT NULL,              -- signed, NOK
    category_id  INTEGER REFERENCES categories(id),
    is_transfer  INTEGER NOT NULL DEFAULT 0 CHECK (is_transfer IN (0, 1)),
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    counterparty TEXT,                           -- Vipps P2P name, when detected
    memo         TEXT,                           -- Vipps memo that drove the category
    note         TEXT,
    batch_id     INTEGER NOT NULL REFERENCES import_batches(id),
    source_row   INTEGER NOT NULL,              -- 1-based row in the source sheet
    is_derived   INTEGER NOT NULL DEFAULT 0 CHECK (is_derived IN (0, 1)),
    -- Same merchant, same day, same amount happens for real (two coffees paid
    -- separately), so the source row number is part of the identity. One source
    -- row can also expand into several derived rows (a loan term split into
    -- interest / principal / fee), hence description+amount in the key too.
    UNIQUE (batch_id, source_row, description, amount)
);

CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_tx_review   ON transactions(needs_review);

-- Real spending, transfers removed. Incoming Vipps nets against its category.
CREATE VIEW IF NOT EXISTS v_spending AS
SELECT c.name AS category, ROUND(SUM(-t.amount), 2) AS spent, COUNT(*) AS n
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.is_transfer = 0 AND c.kind = 'expense'
GROUP BY c.name ORDER BY spent DESC;

CREATE VIEW IF NOT EXISTS v_income AS
SELECT c.name AS category, ROUND(SUM(t.amount), 2) AS received, COUNT(*) AS n
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.is_transfer = 0 AND c.kind = 'income'
GROUP BY c.name ORDER BY received DESC;

CREATE VIEW IF NOT EXISTS v_needs_review AS
SELECT t.date, a.name AS account, t.description, t.amount, c.name AS guessed_category
FROM transactions t
JOIN accounts a ON a.id = t.account_id
LEFT JOIN categories c ON c.id = t.category_id
WHERE t.needs_review = 1 ORDER BY t.date;
