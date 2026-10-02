CREATE TABLE IF NOT EXISTS order_action_idempotency_keys(
  actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  action_type TEXT NOT NULL CHECK(action_type IN ('deliver','revision')),
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  request_fingerprint TEXT NOT NULL,
  result_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(actor_id,idempotency_key),
  CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{8,120}$'),
  CHECK(length(request_fingerprint)=64)
);
CREATE INDEX IF NOT EXISTS idx_order_action_idempotency_created
  ON order_action_idempotency_keys(actor_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_action_idempotency_order
  ON order_action_idempotency_keys(order_id,action_type,created_at DESC);
