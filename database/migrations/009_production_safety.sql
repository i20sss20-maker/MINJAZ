CREATE TABLE IF NOT EXISTS security_rate_events(
  id BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_security_rate_events_lookup ON security_rate_events(kind,key_hash,created_at DESC);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS provider_payment_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_checkout_url TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_checkout_started_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_provider_payment_id ON orders(provider_payment_id) WHERE provider_payment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS payment_adapter_events(
  id BIGSERIAL PRIMARY KEY,
  provider_event_id TEXT UNIQUE NOT NULL,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  provider_payment_id TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_payment_adapter_events_order ON payment_adapter_events(order_id,created_at DESC);

ALTER TABLE freelancer_profiles ADD COLUMN IF NOT EXISTS kyc_provider_reference TEXT;
ALTER TABLE freelancer_profiles ADD COLUMN IF NOT EXISTS kyc_verification_url TEXT;
ALTER TABLE freelancer_profiles ADD COLUMN IF NOT EXISTS kyc_started_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS uq_freelancer_kyc_provider_reference ON freelancer_profiles(kyc_provider_reference) WHERE kyc_provider_reference IS NOT NULL;

CREATE TABLE IF NOT EXISTS kyc_adapter_events(
  id BIGSERIAL PRIMARY KEY,
  provider_event_id TEXT UNIQUE NOT NULL,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
  provider_reference TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_kyc_adapter_events_user ON kyc_adapter_events(user_id,created_at DESC);