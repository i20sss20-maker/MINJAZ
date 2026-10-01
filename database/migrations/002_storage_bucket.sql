ALTER TABLE attachments ADD COLUMN IF NOT EXISTS storage_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_attachments_storage_key ON attachments(storage_key) WHERE storage_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS upload_intents(
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  object_key TEXT UNIQUE NOT NULL,
  file_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL CHECK(size_bytes > 0),
  etag TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_upload_intents_user ON upload_intents(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_upload_intents_expiry ON upload_intents(expires_at) WHERE consumed_at IS NULL;