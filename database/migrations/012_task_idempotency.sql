CREATE TABLE IF NOT EXISTS task_idempotency_keys(
  client_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  task_id BIGINT UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(client_id,idempotency_key),
  CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{8,120}$'),
  CHECK(length(request_fingerprint)=64)
);
CREATE INDEX IF NOT EXISTS idx_task_idempotency_created
  ON task_idempotency_keys(client_id,created_at DESC);
