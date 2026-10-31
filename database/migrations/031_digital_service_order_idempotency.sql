-- An optional per-customer idempotency key prevents duplicate digital-service drafts
-- when a client retries after a network timeout. Existing records remain valid.
BEGIN;
ALTER TABLE digital_service_orders
  ADD COLUMN IF NOT EXISTS request_idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_digital_service_orders_idempotency
  ON digital_service_orders (customer_id, request_idempotency_key)
  WHERE request_idempotency_key IS NOT NULL;
COMMIT;
