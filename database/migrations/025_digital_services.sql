-- MINJAZ: additive digital-services catalog migration (preview first)
BEGIN;
CREATE TABLE IF NOT EXISTS digital_service_packages (
 id BIGSERIAL PRIMARY KEY,
 slug TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]+$'),
 category TEXT NOT NULL CHECK (category IN ('website','mobile_app','ecommerce','branding','maintenance','ai')),
 title_ar TEXT NOT NULL CHECK (length(trim(title_ar)) BETWEEN 3 AND 150),
 description_ar TEXT NOT NULL DEFAULT '',
 price_sar NUMERIC(12,2) NOT NULL CHECK (price_sar >= 0),
 delivery_days INTEGER NOT NULL CHECK (delivery_days BETWEEN 1 AND 365),
 revision_limit INTEGER NOT NULL DEFAULT 2 CHECK (revision_limit BETWEEN 0 AND 50),
 active BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS digital_service_orders (
 id BIGSERIAL PRIMARY KEY,
 package_id BIGINT NOT NULL REFERENCES digital_service_packages(id),
 customer_id BIGINT NOT NULL,
 requirements TEXT NOT NULL CHECK (length(trim(requirements)) BETWEEN 10 AND 10000),
 agreed_price_sar NUMERIC(12,2) NOT NULL CHECK (agreed_price_sar >= 0),
 status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','awaiting_payment','paid','in_progress','delivered','revision_requested','completed','cancelled','refunded')),
 payment_reference TEXT UNIQUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_digital_service_packages_active ON digital_service_packages(category, active);
CREATE INDEX IF NOT EXISTS idx_digital_service_orders_customer ON digital_service_orders(customer_id, created_at DESC);
COMMIT;
