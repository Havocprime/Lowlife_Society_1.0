-- Unique idempotency keys for transactions (ignore NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_idem
ON transactions(idempotency_key)
WHERE idempotency_key IS NOT NULL;
