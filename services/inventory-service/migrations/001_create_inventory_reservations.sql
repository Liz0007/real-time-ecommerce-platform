CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS inventory_reservations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id      UUID NOT NULL UNIQUE,
    status        TEXT NOT NULL,
    reserved_at   TIMESTAMPTZ NOT NULL, -- When this reservation attempt was made. Always set.
    
    -- Reservation deadline after which an unconfirmed reservation should be released
    -- back to available stock. Only set when status = 'inventory_reserved'
    -- (a failed reservation never held stock, so it has nothing to expire).
    expires_at    TIMESTAMPTZ, 

    -- stock returned to inventory after expiring unconfirmed. NULL until a background job (not yet built)
    released_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id ON inventory_reservations (order_id);