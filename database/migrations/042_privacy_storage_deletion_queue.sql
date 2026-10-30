-- Reliable, auditable deletion of uploaded private objects for account-erasure requests.
-- Store the pending S3 key in the same transaction that anonymizes the user.
-- A request is not "completed" until every queued object is actually deleted.
BEGIN;
CREATE TABLE IF NOT EXISTS privacy_storage_deletions (
 id BIGSERIAL PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 privacy_request_id BIGINT NOT NULL REFERENCES privacy_requests(id),
 object_key TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 last_attempt_at TIMESTAMPTZ,
 last_error TEXT,
 deleted_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE (user_id,object_key)
);
CREATE INDEX IF NOT EXISTS idx_privacy_storage_deletions_pending
 ON privacy_storage_deletions(id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_privacy_storage_deletions_request
 ON privacy_storage_deletions(privacy_request_id) WHERE deleted_at IS NULL;
COMMIT;
