import unittest
from pathlib import Path

DOC=(Path(__file__).resolve().parents[1]/'public/digital-services-admin.html').read_text('utf-8')

class AdminPageContractTests(unittest.TestCase):
    def test_admin_login_has_email_and_readiness(self):
        for item in ('id="adminAccess"','id="adminDashboard"','id="adminSetupChecklist"','/api/v1/auth/account-status','/api/v1/auth/login-email'):
            self.assertIn(item,DOC)

    def test_admin_has_no_dev_otp_fallback(self):
        self.assertNotIn('/api/v1/auth/request-otp',DOC)
        self.assertIn('adminLoginAllowed',DOC)

if __name__=='__main__':unittest.main()
