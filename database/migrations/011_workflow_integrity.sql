-- Strengthen workflow integrity at the database layer.
-- Existing unexpected states are normalized before adding constraints.

UPDATE support_tickets
SET status='in_progress', updated_at=now()
WHERE status NOT IN ('open','in_progress','resolved','closed');

ALTER TABLE support_tickets
  DROP CONSTRAINT IF EXISTS support_tickets_status_check;
ALTER TABLE support_tickets
  ADD CONSTRAINT support_tickets_status_check
  CHECK (status IN ('open','in_progress','resolved','closed'));

UPDATE privacy_requests
SET status='in_progress', resolved_at=NULL
WHERE status NOT IN ('pending','in_progress','completed','rejected');

UPDATE privacy_requests
SET resolved_at=NULL
WHERE status IN ('pending','in_progress');

UPDATE privacy_requests
SET resolved_at=COALESCE(resolved_at,now())
WHERE status IN ('completed','rejected');

ALTER TABLE privacy_requests
  DROP CONSTRAINT IF EXISTS privacy_requests_status_check;
ALTER TABLE privacy_requests
  ADD CONSTRAINT privacy_requests_status_check
  CHECK (status IN ('pending','in_progress','completed','rejected'));

CREATE INDEX IF NOT EXISTS idx_support_tickets_status_created
  ON support_tickets(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_privacy_requests_status_created
  ON privacy_requests(status,created_at DESC);
