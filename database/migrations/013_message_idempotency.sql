CREATE TABLE IF NOT EXISTS message_idempotency_keys(
  sender_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  message_id BIGINT UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(sender_id,idempotency_key),
  CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{8,120}$'),
  CHECK(length(request_fingerprint)=64)
);
CREATE INDEX IF NOT EXISTS idx_message_idempotency_created
  ON message_idempotency_keys(sender_id,created_at DESC);
