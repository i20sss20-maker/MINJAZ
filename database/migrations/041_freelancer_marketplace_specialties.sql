-- Freelancer-selected specializations are verifiable structured data, not self-asserted credentials.
-- The old free-text skills field stays intact and no existing projects are changed.
BEGIN;
CREATE TABLE IF NOT EXISTS freelancer_marketplace_specialties (
  user_id BIGINT NOT NULL REFERENCES freelancer_profiles(user_id) ON DELETE CASCADE,
  service_id BIGINT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id,service_id)
);
CREATE INDEX IF NOT EXISTS idx_freelancer_marketplace_specialties_service
 ON freelancer_marketplace_specialties(service_id,user_id);
COMMIT;
