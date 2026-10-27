"""Administration login must reveal configuration blockers, never bypass authorization."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

PAGE=(Path(__file__).resolve().parents[1]/"public/digital-services-admin.html").read_text("utf-8")
class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
    def handle_starttag(self,tag,attrs):
        node=dict(attrs)
        if node.get("id"):self.ids.append(node["id"])

class AdminReadinessScreenTests(unittest.TestCase):
    def test_admin_login_requires_server_capability(self):
        self.assertIn("function adminLoginState(allowed,message)",PAGE)
        self.assertIn("adminLoginAllowed=allowed;",PAGE)
        self.assertIn("$('adminLoginBtn').disabled=!allowed;",PAGE)
        self.assertIn("if(capability.enabled!==true)",PAGE)
        self.assertIn("else if(capability.admin_configured!==true)",PAGE)
        self.assertIn("else if(capability.configured!==true)",PAGE)
        self.assertIn("adminLoginState(true,'إرسال روابط البريد غير مجهز.",PAGE)
        self.assertIn("adminLoginState(false,'تعذّر فحص إعدادات الإدارة.",PAGE)
        self.assertIn("if(!adminLoginAllowed)return showAccess(",PAGE)
        self.assertIn("finally{btn.disabled=!adminLoginAllowed}",PAGE)

    def test_authorized_admin_session_still_opens_dashboard(self):
        self.assertIn("if(data.user?.role==='admin')",PAGE)
        self.assertIn("$('adminDashboard').hidden=false",PAGE)
        self.assertIn("await Promise.all([load(),loadPackages()]);",PAGE)

    def test_setup_message_and_retry_are_accessible(self):
        parser=IdParser()
        parser.feed(PAGE)
        ids=parser.ids
        for name in ("adminAccess","adminDashboard","adminSetupChecklist",
                     "adminLoginBtn","adminEmailForm","accessStatus","recheckAdmin"):
            self.assertEqual(ids.count(name),1,name)
        self.assertIn('id="adminSetupChecklist" class="hint muted" role="status" aria-live="polite"',PAGE)
        self.assertIn("$('recheckAdmin').addEventListener('click',checkAdminAccess)",PAGE)
        self.assertIn("ADMIN_EMAIL",PAGE)

    def test_never_fallback_to_dev_otp(self):
        self.assertIn("'/api/v1/auth/login-email'",PAGE)
        self.assertNotIn("/api/v1/auth/request-otp",PAGE)
        self.assertNotIn("dev_code",PAGE)
        self.assertNotIn("pendingChallenge",PAGE)

if __name__=="__main__":unittest.main()
