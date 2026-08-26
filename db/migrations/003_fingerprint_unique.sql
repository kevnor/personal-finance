CREATE UNIQUE INDEX idx_tx_identity
    ON transactions(account_id, fingerprint, occurrence)
    WHERE is_derived = 0 AND fingerprint <> '';
