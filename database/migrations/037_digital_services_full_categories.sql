-- Additional preview-first digital service categories. Data is seeded separately,
-- and no payments or production package records are created by this migration.
BEGIN;
ALTER TABLE digital_service_packages DROP CONSTRAINT IF EXISTS digital_service_packages_category_check;
ALTER TABLE digital_service_packages ADD CONSTRAINT digital_service_packages_category_check
  CHECK (category IN ('website','mobile_app','ecommerce','branding','maintenance','ai','marketing','seo','content','video','automation','data','security','consulting'));
COMMIT;
