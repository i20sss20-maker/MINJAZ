-- Additive migration: preserve revision audit history and enforce owner reference.
BEGIN;
CREATE TABLE IF NOT EXISTS digital_service_revisions (
 id BIGSERIAL PRIMARY KEY,
 order_id BIGINT NOT NULL REFERENCES digital_service_orders(id),
 customer_id BIGINT NOT NULL,
 note TEXT NOT NULL CHECK (length(trim(note)) BETWEEN 10 AND 3000),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_digital_service_revisions_order ON digital_service_revisions(order_id, created_at);
COMMIT;
