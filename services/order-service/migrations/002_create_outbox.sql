-- migrations/002_create_outbox.sql

CREATE TABLE IF NOT EXISTS outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  TEXT NOT NULL,        -- e.g. 'order'
    aggregate_id    UUID NOT NULL,        -- the order's id
    event_type      TEXT NOT NULL,        -- e.g. 'order.created'
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ,          -- NULL until published
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT
);

-- Fast lookup of unpublished rows, oldest first
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox (created_at)
    WHERE published_at IS NULL;
