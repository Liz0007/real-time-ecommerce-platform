CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS payments (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id                  UUID NOT NULL UNIQUE,
    status                    TEXT NOT NULL,
    amount                    NUMERIC(12, 2),
    payment_method            TEXT,
    provider_transaction_id   TEXT,
    failure_reason            TEXT,
    processed_at              TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments (order_id);