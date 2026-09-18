CREATE TABLE IF NOT EXISTS order_fulfillment_state (
    order_id          UUID PRIMARY KEY REFERENCES orders(id),
    payment_status    TEXT,
    inventory_status  TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);