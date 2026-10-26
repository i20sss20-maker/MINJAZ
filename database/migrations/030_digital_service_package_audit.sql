-- Preview-first package management change log. Never changes payment configuration.
BEGIN;
CREATE TABLE IF NOT EXISTS digital_service_package_events (
  id BIGSERIAL PRIMARY KEY,
  package_id BIGINT NOT NULL REFERENCES digital_service_packages(id) ON DELETE RESTRICT,
  admin_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  action TEXT NOT NULL CHECK (action IN ('created','updated')),
  before_data JSONB,
  after_data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_digital_service_package_events_package
 ON digital_service_package_events(package_id,id DESC);
COMMIT;
