-- Persist read position for first-party customer order notifications.
-- Strictly nonfinancial and scoped to the currently authenticated customer.
BEGIN;
CREATE TABLE IF NOT EXISTS digital_service_notification_reads (
 customer_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 last_seen_event_id BIGINT NOT NULL DEFAULT 0 CHECK (last_seen_event_id >= 0),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
