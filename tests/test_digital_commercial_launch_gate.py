"""MINJAZ financial go-live invariants: never claim transfers were made without PSP proof.
These tests intentionally inspect launch gate and route code without live credentials.
"""
import re
import unittest
from pathlib import Path

SERVER = (Path(__file__).resolve().parents[1]/"server.py").read_text("utf-8")

class LaunchGuardTests(unittest.TestCase):
    def test_email_only_policy_and_administrator_required(self):
        self.assertIn("if not EMAIL_AUTH_REQUIRED:",SERVER)
        self.assertIn("blockers.append('VERIFIED_EMAIL_POLICY')",SERVER)
        self.assertIn("blockers.append('ADMIN_EMAIL')",SERVER)
        self.assertIn("'key':'verified_email_policy'",SERVER)
        self.assertIn("'key':'admin_email_configured'",SERVER)
        self.assertRegex(SERVER,r"'key':'email_provider'[^\n]+?'required':True")

    def test_payout_mark_paid_rejected_without_transfer_evidence(self):
        self.assertIn("if st=='paid' and APP_ENV!='preview':",SERVER)
        self.assertIn("'error':'verified_payout_provider_required'",SERVER)
        self.assertIn("'MARKETPLACE_PAYOUT_SETTLEMENT_NOT_IMPLEMENTED'",SERVER)
        self.assertRegex(SERVER,r"'key':'marketplace_payout_settlement'[^\n]+?'required':True")
        self.assertIn("'value':'no_verified_payout_adapter'",SERVER)
        self.assertIn("if IS_PROD:",SERVER)
        self.assertIn("_prod_blockers=production_blockers()",SERVER)

    def test_mock_payment_rejected_in_production(self):
        self.assertIn("if IS_PROD:return self.sendj(503,{'error':'mock_payment_disabled'})",SERVER)
        self.assertIn("if PAYMENT_MODE!='adapter' or len(PAYMENT_WEBHOOK_SECRET)<32",SERVER)
        self.assertIn("hmac.compare_digest",SERVER)

    def test_no_bypass_using_manual_admin_update(self):
        route=SERVER.split("if p=='/api/admin/payouts' and method=='GET':",1)[1].split("if p=='/api/admin/support'",1)[0]
        deny=route.find("if st=='paid' and APP_ENV!='preview':")
        mutate=route.find("update_payout_status(pid,st,b.get('admin_note'))")
        self.assertGreaterEqual(deny,0)
        self.assertGreater(mutate,deny)

if __name__=="__main__": unittest.main()
