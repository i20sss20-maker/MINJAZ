ALTER TABLE account_request_idempotency_keys
  DROP CONSTRAINT IF EXISTS account_request_idempotency_keys_request_kind_check;

ALTER TABLE account_request_idempotency_keys
  ADD CONSTRAINT account_request_idempotency_keys_request_kind_check
  CHECK(request_kind IN ('support','privacy','safety','saved_search'));
