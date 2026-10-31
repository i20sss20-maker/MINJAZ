-- Sandbox digital-service delivery artifacts. These are secure pointers to existing HTTPS files,
-- not file uploads or public CDN objects. They become visible to customers only after delivery.
BEGIN;
CREATE TABLE IF NOT EXISTS digital_service_deliverables (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES digital_service_orders(id) ON DELETE RESTRICT,
  admin_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 3 AND 120),
  url TEXT NOT NULL CHECK (length(url) BETWEEN 12 AND 2000 AND url LIKE 'https://%'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_digital_service_deliverables_order
  ON digital_service_deliverables(order_id,id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_digital_service_deliverables_unique_url
  ON digital_service_deliverables(order_id,url);
COMMIT;
