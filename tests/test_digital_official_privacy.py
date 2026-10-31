"""Production release privacy invariant checks (no sensitive data printed)."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/'server.py').read_text(encoding='utf-8')
READINESS=(ROOT/'scripts'/'check_minjaz_launch_readiness.py').read_text(encoding='utf-8')

class OfficialPrivacySafety(unittest.TestCase):
    def test_deleted_email_identity_is_erased(self):
        start=SERVER.index('def execute_account_deletion(')
        end=SERVER.index('\ndef update_privacy_request(',start)
        block=SERVER[start:end]
        for q in (
            'u.email original_email',
            'original_email=str(pr.get(\'original_email\')',
            'delete from account_email_actions where user_id=%s',
            'delete from email_login_challenges where email=%s',
            'email=null,password_hash=null,email_verified_at=null',
            'delete from sessions where user_id=%s',
            'delete from user_roles where user_id=%s',
        ):
            self.assertIn(q,block)
        self.assertIn('active_orders',block)
        self.assertIn('active_payouts',block)
        self.assertIn('admin_deletion_requires_security_review',block)

    def test_unverified_storage_removal_never_counts_as_launch_ready(self):
        self.assertIn("'key':'privacy_account_deletion','ok':False",SERVER)
        self.assertIn('storage_object_deletion_and_restore_drill_unverified',SERVER)
        self.assertIn('privacy_account_deletion',READINESS)
        self.assertIn('raise RuntimeError("Commercial launch blocked: account-deletion privacy review incomplete")',READINESS)

    def test_payment_and_kyc_fakes_never_pass_launch_guard(self):
        self.assertIn('MARKETPLACE_PAYOUT_SETTLEMENT_NOT_IMPLEMENTED',SERVER)
        self.assertIn("'key':'marketplace_payout_settlement','ok':False",SERVER)
        self.assertIn('if IS_PROD:',SERVER)
        self.assertIn("if _prod_blockers:",SERVER)
        self.assertIn("'key':'legal_review'",SERVER)

if __name__=='__main__':
    unittest.main()
