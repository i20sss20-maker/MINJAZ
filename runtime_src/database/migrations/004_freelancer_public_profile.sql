CREATE TABLE IF NOT EXISTS freelancer_portfolio_items(
  id BIGSERIAL PRIMARY KEY,
  freelancer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  external_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_freelancer_portfolio_items_freelancer
  ON freelancer_portfolio_items(freelancer_id, created_at DESC);

CREATE TABLE IF NOT EXISTS task_invitations(
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  client_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  freelancer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  note TEXT,
  status TEXT NOT NULL DEFAULT 'sent' CHECK(status IN ('sent','viewed','declined')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(task_id, freelancer_id)
);
CREATE INDEX IF NOT EXISTS idx_task_invitations_freelancer
  ON task_invitations(freelancer_id,status,created_at DESC);