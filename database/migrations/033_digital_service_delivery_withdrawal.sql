-- Preserve a record of withdrawn draft delivery links. Published links cannot be withdrawn.
BEGIN;
ALTER TABLE digital_service_deliverables
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS archived_by BIGINT REFERENCES users(id);
DROP INDEX IF EXISTS idx_digital_service_deliverables_unique_url;
CREATE UNIQUE INDEX IF NOT EXISTS idx_digital_service_deliverables_active_url
  ON digital_service_deliverables(order_id,url) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_digital_service_deliverables_archived
  ON digital_service_deliverables(order_id,archived_at) WHERE archived_at IS NOT NULL;
COMMIT;
