ALTER TABLE freelancer_portfolio_items
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_idempotency
  ON freelancer_portfolio_items(freelancer_id,idempotency_key)
  WHERE idempotency_key IS NOT NULL;

ALTER TABLE freelancer_portfolio_items
  DROP CONSTRAINT IF EXISTS freelancer_portfolio_items_idempotency_key_check;

ALTER TABLE freelancer_portfolio_items
  ADD CONSTRAINT freelancer_portfolio_items_idempotency_key_check
  CHECK(idempotency_key IS NULL OR idempotency_key ~ '^[A-Za-z0-9._:-]{8,120}$');

ALTER TABLE freelancer_portfolio_items
  DROP CONSTRAINT IF EXISTS freelancer_portfolio_items_request_fingerprint_check;

ALTER TABLE freelancer_portfolio_items
  ADD CONSTRAINT freelancer_portfolio_items_request_fingerprint_check
  CHECK(request_fingerprint IS NULL OR length(request_fingerprint)=64);
