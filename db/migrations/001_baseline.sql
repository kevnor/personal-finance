CREATE TABLE IF NOT EXISTS schema_migrations (
    name       TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('bank', 'credit_card'))
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
    date         TEXT    NOT NULL,
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    description  TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    category_id  INTEGER REFERENCES categories(id),
    is_transfer  INTEGER NOT NULL DEFAULT 0 CHECK (is_transfer IN (0, 1)),
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    counterparty TEXT,
    memo         TEXT,
    note         TEXT,
    batch_id     INTEGER NOT NULL REFERENCES import_batches(id),
    source_row   INTEGER NOT NULL,
    is_derived   INTEGER NOT NULL DEFAULT 0 CHECK (is_derived IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_tx_review   ON transactions(needs_review);
