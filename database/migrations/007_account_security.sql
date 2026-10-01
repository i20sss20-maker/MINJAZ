ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_agent TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS device_label TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS ip_hash TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

UPDATE sessions
SET last_seen_at=COALESCE(last_seen_at,created_at),
    device_label=COALESCE(NULLIF(device_label,''),'جلسة سابقة')
WHERE last_seen_at IS NULL OR device_label IS NULL OR device_label='';

CREATE INDEX IF NOT EXISTS idx_sessions_user_active
  ON sessions(user_id, revoked_at, expires_at, last_seen_at DESC);
