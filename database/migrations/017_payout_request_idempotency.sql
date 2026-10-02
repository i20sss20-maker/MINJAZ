ALTER TABLE payout_requests
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

ALTER TABLE payout_requests
  ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_payout_requests_idempotency
  ON payout_requests(freelancer_id,idempotency_key)
  WHERE idempotency_key IS NOT NULL;
