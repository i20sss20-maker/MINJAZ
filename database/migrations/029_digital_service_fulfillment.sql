-- Preview-first digital service fulfillment and immutable status history.
BEGIN;
ALTER TABLE digital_service_orders ADD COLUMN IF NOT EXISTS delivery_note TEXT;
CREATE TABLE IF NOT EXISTS digital_service_order_events (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES digital_service_orders(id) ON DELETE RESTRICT,
  actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  previous_status TEXT NOT NULL,
  new_status TEXT NOT NULL,
  note TEXT CHECK (note IS NULL OR length(note) <= 3000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_digital_service_order_events_order
  ON digital_service_order_events(order_id, id DESC);
COMMIT;
