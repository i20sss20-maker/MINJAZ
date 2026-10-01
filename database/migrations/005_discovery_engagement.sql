CREATE TABLE IF NOT EXISTS client_profiles(
  user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  company_name TEXT,
  bio TEXT,
  city TEXT,
  sector TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS favorite_tasks(
  freelancer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(freelancer_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_favorite_tasks_freelancer ON favorite_tasks(freelancer_id, created_at DESC);

CREATE TABLE IF NOT EXISTS saved_task_searches(
  id BIGSERIAL PRIMARY KEY,
  freelancer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  filters JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_saved_task_searches_freelancer ON saved_task_searches(freelancer_id, created_at DESC);

ALTER TABLE user_notifications_v2 ADD COLUMN IF NOT EXISTS task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_user_notifications_v2_task ON user_notifications_v2(user_id, task_id, created_at DESC) WHERE task_id IS NOT NULL;