-- Enforce ownership against the existing MINJAZ users BIGSERIAL primary key.
-- Run on isolated preview after 025-027; validation fails if orphan rows exist.
BEGIN;
ALTER TABLE digital_service_orders
  ADD CONSTRAINT digital_service_orders_customer_fk
  FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE RESTRICT;
COMMIT;
