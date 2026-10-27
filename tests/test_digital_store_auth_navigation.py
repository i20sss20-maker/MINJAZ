"""Storefront guest recovery and verified-email sign-in return path."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STORE=(ROOT/"public/digital-services.html").read_text("utf-8")
AUTH=(ROOT/"public/minjaz-account-registration-v1.js").read_text("utf-8")

class DigitalStorefrontAuthTests(unittest.TestCase):
    def test_catalog_has_visible_login_route_on_all_screen_sizes(self):
        self.assertIn('class="auth-link"',STORE)
        self.assertIn('href="/?auth=login&amp;next=digital-services"',STORE)
        self.assertIn("display:none}.auth-link{margin-inline-start:auto",STORE)
        self.assertIn('href="/?auth=login&amp;next=digital-services">سجّل لطلب الخدمة',STORE)

    def test_unauthorized_guest_gets_action_not_only_error(self):
        self.assertIn("function signInLink()",STORE)
        self.assertIn("error.code='unauthorized'",STORE)
        self.assertIn("if(e.code==='unauthorized')box.append(signInLink())",STORE)
        self.assertIn("if(error.code==='unauthorized')box.append(signInLink())",STORE)
        self.assertIn("if(err.code==='unauthorized')$('formError').append(signInLink())",STORE)
        self.assertIn("'/api/digital-services/orders'",STORE)

    def test_email_login_redirects_only_to_fixed_internal_page(self):
        self.assertIn('authQuery.get("auth")==="login"',AUTH)
        self.assertIn('authQuery.get("next")==="digital-services"',AUTH)
        self.assertIn('destination!=="digital-services"',AUTH)
        self.assertIn('window.location.assign("/digital-services")',AUTH)
        self.assertIn('if(typeof me==="undefined" || !me || !me.user)return;',AUTH)
        self.assertNotIn("window.location.assign(destination)",AUTH)
        self.assertNotIn('window.location.assign(authQuery.get(',AUTH)
        self.assertIn("returnToStoreAfterLogin();",AUTH)
        self.assertIn("method:'POST'",STORE)

    def test_no_public_payment_promise(self):
        self.assertIn("لا توجد معاملات دفع حقيقية",STORE)
        self.assertIn("سيُحفظ الطلب كمسودة فقط",STORE)

if __name__=="__main__":unittest.main()
