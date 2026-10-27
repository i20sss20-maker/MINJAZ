"""MINJAZ marketplace and digital storefront are connected for all roles."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUTH=(ROOT/"public/minjaz-account-registration-v1.js").read_text("utf-8")
STORE=(ROOT/"public/digital-services.html").read_text("utf-8")
MAIN=(ROOT/"public/index.html").read_text("utf-8")

class UnifiedDigitalStoreNavigationTests(unittest.TestCase):
    def test_guest_can_browse_services_without_account_or_payment(self):
        self.assertIn('class="minjaz-service-entry minjaz-service-entry-auth" href="/digital-services"',AUTH)
        self.assertIn("تقدر تتصفح الباقات والأسعار قبل إنشاء الحساب",AUTH)
        self.assertIn("لا تشمل دفعًا حقيقيًا",AUTH)
        self.assertIn("استكشف الخدمات الجاهزة",AUTH)
        self.assertIn("const tpl=",AUTH)

    def test_every_signed_in_role_can_find_catalog(self):
        self.assertIn('const appTopbar=document.querySelector("#app .topbar")',AUTH)
        self.assertIn('if(appTopbar&&!document.getElementById("minjazServiceEntryApp"))',AUTH)
        self.assertIn('link.href="/digital-services"',AUTH)
        self.assertIn('link.className="minjaz-service-entry minjaz-service-entry-app"',AUTH)
        self.assertIn('appTopbar.insertBefore(link,chip)',AUTH)
        for role in ("client","freelancer","admin"):
            self.assertIn(role,MAIN)

    def test_accessible_links_and_responsive_design(self):
        self.assertIn('link.setAttribute("aria-label"',AUTH)
        self.assertIn(".minjaz-service-entry:focus-visible",AUTH)
        self.assertIn("@media(max-width:720px)",AUTH)
        self.assertIn("@media(max-width:430px)",AUTH)
        self.assertIn("prefers-reduced-motion:reduce",AUTH)

    def test_existing_account_and_store_signin_unmodified(self):
        self.assertIn('returnToStoreAfterLogin();',AUTH)
        self.assertIn('"/api/v1/auth/login-email"',AUTH)
        self.assertIn('"/api/v1/auth/register"',AUTH)
        self.assertIn('a.href=\'/?auth=login&next=digital-services\'',STORE)
        self.assertNotIn('window.location.assign(link.href)',AUTH)

if __name__=="__main__":unittest.main()
