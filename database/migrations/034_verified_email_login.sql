-- Enable independent, verified email identities without altering existing phone identities.
-- Phone-only users retain their accounts; they are not implicitly merged with
-- newly verified email accounts because that could expose historical orders.
BEGIN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ALTER COLUMN phone DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_minjaz_users_email_login
  ON users (email) WHERE email IS NOT NULL;
CREATE TABLE IF NOT EXISTS email_login_challenges (
  id BIGSERIAL PRIMARY KEY,
  challenge_id UUID NOT NULL UNIQUE,
  email TEXT NOT NULL,
  requested_role TEXT NOT NULL CHECK (requested_role IN ('client','freelancer')),
  code_hash TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  expires_at TIMESTAMPTZ NOT NULL,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_minjaz_email_login_recent
  ON email_login_challenges(email,created_at DESC);
COMMIT;
