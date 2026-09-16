CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS inventory_reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id     UUID NOT NULL UNIQUE,
    status       TEXT NOT NULL,
    reserved_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id ON inventory_reservations (order_id);