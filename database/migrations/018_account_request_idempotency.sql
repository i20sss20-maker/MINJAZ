CREATE TABLE IF NOT EXISTS account_request_idempotency_keys(
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  request_kind TEXT NOT NULL CHECK(request_kind IN ('support','privacy')),
  request_fingerprint TEXT NOT NULL,
  result_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id,idempotency_key),
  CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{8,120}$'),
  CHECK(length(request_fingerprint)=64)
);
CREATE INDEX IF NOT EXISTS idx_account_request_idem_created
  ON account_request_idempotency_keys(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_account_request_idem_kind
  ON account_request_idempotency_keys(user_id,request_kind,created_at DESC);
