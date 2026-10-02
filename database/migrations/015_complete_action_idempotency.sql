ALTER TABLE order_action_idempotency_keys
  DROP CONSTRAINT IF EXISTS order_action_idempotency_keys_action_type_check;

ALTER TABLE order_action_idempotency_keys
  ADD CONSTRAINT order_action_idempotency_keys_action_type_check
  CHECK(action_type IN ('deliver','revision','complete'));
