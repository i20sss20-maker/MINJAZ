-- A deliberately separate action is required to elevate an already-verified
-- existing owner's account. No automatic elevation on login or config update.
BEGIN;
ALTER TABLE account_email_actions
  DROP CONSTRAINT IF EXISTS account_email_actions_action_check;
ALTER TABLE account_email_actions
  ADD CONSTRAINT account_email_actions_action_check
  CHECK (action IN ('verify','reset','admin_claim'));
COMMIT;
