ALTER TABLE categories ADD COLUMN budget_treatment TEXT NOT NULL DEFAULT 'variable'
    CHECK (budget_treatment IN ('fixed','variable','exceptional'));

-- Read ONLY for categories whose kind = 'transfer'; ignored otherwise.
ALTER TABLE categories ADD COLUMN cash_treatment TEXT NOT NULL DEFAULT 'settlement'
    CHECK (cash_treatment IN ('committed','settlement','savings'));

ALTER TABLE transactions ADD COLUMN budget_override TEXT
    CHECK (budget_override IN ('fixed','variable','exceptional','reimbursable','ignore'));

ALTER TABLE transactions ADD COLUMN origin TEXT NOT NULL DEFAULT 'import'
    CHECK (origin IN ('manual','import','bank','derived'));

ALTER TABLE transactions ADD COLUMN fingerprint TEXT NOT NULL DEFAULT '';

ALTER TABLE transactions ADD COLUMN occurrence INTEGER NOT NULL DEFAULT 1;

CREATE TABLE reimbursements (
    id                        INTEGER PRIMARY KEY,
    transaction_id            INTEGER NOT NULL REFERENCES transactions(id),
    expected_from             TEXT    NOT NULL,
    expected_amount           REAL    NOT NULL,
    settled_by_transaction_id INTEGER REFERENCES transactions(id),
    settled_at                TEXT,
    note                      TEXT
);

CREATE TABLE merchant_rules (
    id          INTEGER PRIMARY KEY,
    pattern     TEXT    NOT NULL UNIQUE,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    created_at  TEXT    NOT NULL
);

CREATE TABLE budget_config (
    id             INTEGER PRIMARY KEY,
    effective_from TEXT    NOT NULL,
    income_mode    TEXT    NOT NULL CHECK (income_mode IN ('derived','manual')),
    fixed_mode     TEXT    NOT NULL CHECK (fixed_mode  IN ('derived','manual')),
    manual_income  REAL,
    manual_fixed   REAL,
    savings_target REAL    NOT NULL,
    week_starts_on INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_tx_fingerprint ON transactions(fingerprint);
