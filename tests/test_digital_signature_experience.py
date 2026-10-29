"""Arabic-first signature experience contracts without fake marketplace data.

Checks the real HTML entrypoints, accessibility, and server paths without
network calls, user accounts or simulated payment transactions.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
PUB=ROOT/"public"
SERVER=(ROOT/"server.py").read_text(encoding="utf-8")
SMOKE=(ROOT/"scripts"/"check_minjaz_launch_readiness.py").read_text(encoding="utf-8")
LANDING=(PUB/"discover.html").read_text(encoding="utf-8")
SIGNUP=(PUB/"signup.html").read_text(encoding="utf-8")
WORKSPACE=(PUB/"workspace.html").read_text(encoding="utf-8")
STORE=(PUB/"digital-services.html").read_text(encoding="utf-8")
ADMIN=(PUB/"digital-services-admin.html").read_text(encoding="utf-8")
PRIVACY=(PUB/"privacy.html").read_text(encoding="utf-8")
DELETION=(PUB/"account-deletion.html").read_text(encoding="utf-8")
CSS=(PUB/"minjaz-signature.css").read_text(encoding="utf-8")


class SignatureExperience(unittest.TestCase):
    def test_all_pages_use_consistent_real_brand_assets(self):
        for source in (LANDING,SIGNUP,WORKSPACE,STORE,ADMIN,PRIVACY,DELETION):
            self.assertIn('href="/minjaz-signature.css?v=1"',source)
            self.assertIn('href="/icon.svg"',source)
            self.assertIn('lang="ar" dir="rtl"',source)
            self.assertIn("<title>",source)
            self.assertIn("مِنجاز",source)
        self.assertIn('class="minjaz-auth"',SIGNUP)
        self.assertIn('class="minjaz-work"',WORKSPACE)
        self.assertIn('class="minjaz-market"',LANDING)
        self.assertIn('class="minjaz-market"',STORE)
        self.assertIn('class="minjaz-ops"',ADMIN)
        self.assertIn('class="minjaz-doc"',PRIVACY)

    def test_visual_system_is_responsive_keyboard_usable_and_not_fake(self):
        for token in ("Alexandria","IBM+Plex+Sans+Arabic",
                      "prefers-reduced-motion","focus-visible",
                      "max-width:820px","max-width:580px"):
            self.assertIn(token,CSS)
        self.assertIn("max-width:520px",LANDING)
        self.assertIn('href="#main"',LANDING)
        self.assertIn('aria-label="أقسام الصفحة"',LANDING)
        self.assertIn('aria-labelledby="hero-title"',LANDING)
        self.assertIn('لا يتم تحصيل أي مبالغ حاليًا',WORKSPACE)
        self.assertIn('التعاملات المالية لم تُفعّل بعد',LANDING)
        for fake in ("٤٫٩/٥","+10,000","عملاء موثّقون","مدفوع بالكامل","100% آمن"):
            self.assertNotIn(fake,LANDING)

    def test_preview_homepage_uses_functional_real_account_entrypoint(self):
        self.assertIn("p in ('/discover','/discover/')",SERVER)
        self.assertIn("p in ('/classic','/classic/')",SERVER)
        self.assertIn("front='discover.html' if APP_ENV=='preview' and p=='/'",SERVER)
        self.assertIn("open(HTML_PATH,'rb').read()",SERVER)
        self.assertIn("p=='/minjaz-signature.css'",SERVER)
        self.assertIn("self._headers(200,'text/css; charset=utf-8')",SERVER)
        self.assertIn("premium_home=",SMOKE)
        self.assertIn('href="/signup?role=client"',LANDING)
        self.assertIn('href="/signup?role=freelancer"',LANDING)
        self.assertIn('href="/workspace"',LANDING)
        self.assertIn('chosenRole=entryQuery.get("role")',SIGNUP)
        self.assertIn('value="'+chr(39)+'+chosenRole+'+chr(39)+'"',SIGNUP)
        self.assertIn('await call("/api/v1/auth/login-email"',SIGNUP)
        self.assertIn('await call("/api/v1/auth/register"',SIGNUP)
        self.assertIn('href="/signup?auth=login"',DELETION)

    def test_direct_login_entrypoint_uses_verified_email_without_old_otp(self):
        self.assertIn("p in ('/signup','/signup/','/login','/login/')",SERVER)
        self.assertIn("if APP_ENV!='preview': return self.sendj(404",SERVER)
        self.assertIn(r'/^\/login\/?$/.test(window.location.pathname)',SIGNUP)
        self.assertIn('show("login")',SIGNUP)
        self.assertIn('await call("/api/v1/auth/login-email"',SIGNUP)
        self.assertNotIn('window.location.assign("/")',SIGNUP)

    def test_existing_live_workspace_ids_are_preserved(self):
        for ident in (
            "logout","notice","loginRequired","loading","workspace",
            "welcome","who","switchRole","newTask","taskItems","sideItems",
            "orderItems","profile","ownerAdminPanel","offersDialog",
            "orderDialog","messageForm","clientProfile","freelancerProfile",
            "launchReadinessPanel"
        ):
            # Profile is an anchor name in some surfaces, not necessarily an id
            if ident=="profile":
                self.assertIn('href="#profile"',WORKSPACE)
            else:
                self.assertIn('id="'+ident+'"',WORKSPACE)
        self.assertIn('src="/workspace-v1.js" defer',WORKSPACE)

    def test_critical_interface_ids_are_unique(self):
        for name,source in (("signup",SIGNUP),("workspace",WORKSPACE),
                            ("landing",LANDING),("store",STORE),("admin",ADMIN)):
            ids=re.findall(r'\bid="([^"]+)"',source)
            self.assertEqual(len(ids),len(set(ids)),name+" has duplicate IDs")

    def test_deletion_and_account_links_are_real_not_old_otp_landing(self):
        self.assertNotIn('href="/?delete_account=1"',DELETION)
        self.assertNotIn('href="/?auth=login"',ADMIN)
        self.assertIn('href="/signup?auth=login"',ADMIN)
        self.assertIn('href="/privacy"',DELETION)
        self.assertIn('class="doc-nav"',PRIVACY)
        self.assertIn('class="doc-nav"',DELETION)


if __name__=="__main__":
    unittest.main()
,SIGNUP)
        self.assertIn('show("login")',SIGNUP)
        self.assertIn('await call("/api/v1/auth/login-email"',SIGNUP)
        self.assertNotIn('window.location.assign("/")',SIGNUP)

    def test_existing_live_workspace_ids_are_preserved(self):
        for ident in (
            "logout","notice","loginRequired","loading","workspace",
            "welcome","who","switchRole","newTask","taskItems","sideItems",
            "orderItems","profile","ownerAdminPanel","offersDialog",
            "orderDialog","messageForm","clientProfile","freelancerProfile",
            "launchReadinessPanel"
        ):
            # Profile is an anchor name in some surfaces, not necessarily an id
            if ident=="profile":
                self.assertIn('href="#profile"',WORKSPACE)
            else:
                self.assertIn('id="'+ident+'"',WORKSPACE)
        self.assertIn('src="/workspace-v1.js" defer',WORKSPACE)

    def test_critical_interface_ids_are_unique(self):
        for name,source in (("signup",SIGNUP),("workspace",WORKSPACE),
                            ("landing",LANDING),("store",STORE),("admin",ADMIN)):
            ids=re.findall(r'\bid="([^"]+)"',source)
            self.assertEqual(len(ids),len(set(ids)),name+" has duplicate IDs")

    def test_deletion_and_account_links_are_real_not_old_otp_landing(self):
        self.assertNotIn('href="/?delete_account=1"',DELETION)
        self.assertNotIn('href="/?auth=login"',ADMIN)
        self.assertIn('href="/signup?auth=login"',ADMIN)
        self.assertIn('href="/privacy"',DELETION)
        self.assertIn('class="doc-nav"',PRIVACY)
        self.assertIn('class="doc-nav"',DELETION)


if __name__=="__main__":
    unittest.main()
