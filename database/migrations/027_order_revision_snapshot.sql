-- Run only after 025 and 026. Existing orders inherit the package limit once.
BEGIN;
ALTER TABLE digital_service_orders ADD COLUMN IF NOT EXISTS agreed_revision_limit INTEGER;
UPDATE digital_service_orders AS o
SET agreed_revision_limit = p.revision_limit
FROM digital_service_packages AS p
WHERE o.package_id = p.id AND o.agreed_revision_limit IS NULL;
ALTER TABLE digital_service_orders ALTER COLUMN agreed_revision_limit SET NOT NULL;
ALTER TABLE digital_service_orders ADD CONSTRAINT agreed_revision_limit_range CHECK (agreed_revision_limit BETWEEN 0 AND 50);
COMMIT;
