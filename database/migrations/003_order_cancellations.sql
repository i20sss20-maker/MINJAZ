CREATE TABLE IF NOT EXISTS order_cancellation_requests(
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  requested_by BIGINT NOT NULL REFERENCES users(id),
  reason TEXT NOT NULL,
  details TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in_review','approved','rejected')),
  previous_order_status TEXT,
  previous_task_status TEXT,
  payment_status_at_request TEXT,
  refund_status TEXT NOT NULL DEFAULT 'not_needed' CHECK(refund_status IN ('not_needed','pending','manual_required','refunded')),
  admin_note TEXT,
  resolved_by BIGINT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_order_cancellations_order ON order_cancellation_requests(order_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_cancellations_status ON order_cancellation_requests(status,created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_order_cancellation_active ON order_cancellation_requests(order_id) WHERE status IN ('pending','in_review');
