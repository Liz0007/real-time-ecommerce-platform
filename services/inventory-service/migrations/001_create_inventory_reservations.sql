CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS inventory_reservations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id      UUID NOT NULL UNIQUE,
    status        TEXT NOT NULL,
    reserved_at   TIMESTAMPTZ NOT NULL, -- When this reservation attempt was made. Always set.
    
    -- Deadline after which an unconfirmed reservation should be released
    -- back to available stock. Only set when status = 'inventory_reserved'
    -- (a failed reservation never held stock, so it has nothing to expire).
    expires_at    TIMESTAMPTZ, 

    -- When the reservation was actually released back to stock after
    -- expiring unconfirmed. NULL until a background job (not yet built)
    -- processes expired reservations — never set directly by the consumer
    -- that creates the reservation.
    released_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id ON inventory_reservations (order_id);