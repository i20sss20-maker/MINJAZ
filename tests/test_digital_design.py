"""Guard the MINJAZ design refresh against broken controls and missing anchors.

Tests the real HTML documents that the preview container serves; avoids making
network calls or changing any database.
"""
import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "public"

class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.named_tags = {}
        self.anchors = []
        self.headings = []
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
            self.named_tags[attrs["id"]] = tag
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.anchors.append(attrs["href"][1:])
        if tag in ("h1", "h2"):
            self.headings.append(tag)

class DigitalDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = (ROOT / "digital-services.html").read_text(encoding="utf8")
        cls.admin = (ROOT / "digital-services-admin.html").read_text(encoding="utf8")
        cls.store_page = Page(cls.store)
        cls.admin_page = Page(cls.admin)

    def test_core_client_freelancer_and_admin_share_one_stylesheet(self):
        main = (ROOT / "index.html").read_text(encoding="utf8")
        style = (ROOT / "minjaz-unified-ui-v1.css").read_text(encoding="utf8")
        self.assertIn('id="minjazUnifiedDesign"', main)
        self.assertIn('href="/minjaz-unified-ui-v1.css"', main)
        self.assertIn("html[data-minjaz-role=\"client\"]", style)
        self.assertIn("html[data-minjaz-role=\"freelancer\"]", style)
        self.assertIn("html[data-minjaz-role=\"admin\"]", style)
        self.assertIn("document.documentElement.dataset.minjazRole=me.user.role", main)
        self.assertGreater(len(style), 15000)

    def test_core_main_pages_and_role_navigation_exist(self):
        main = (ROOT / "index.html").read_text(encoding="utf8")
        for page in ("auth", "app", "home", "tasks", "orders", "team", "account", "admin"):
            with self.subTest(page=page):
                self.assertRegex(main, r'id="'+page+'"')
        for role in ("client", "freelancer", "admin"):
            with self.subTest(role=role):
                self.assertIn(role + ":[", main)

    def test_unified_theme_respects_mobile_and_dark_mode(self):
        style = (ROOT / "minjaz-unified-ui-v1.css").read_text(encoding="utf8")
        for marker in ('html[data-theme="dark"]', '.mobileNav', '.authPanel',
                       '.heroStats', '.filesHeroV30', '.inboxHeroV29',
                       '@media(max-width:980px)', '@media(max-width:430px)',
                       'prefers-reduced-motion', 'focus-visible'):
            with self.subTest(marker=marker):
                self.assertIn(marker, style)

    def test_no_duplicate_dom_ids(self):
        for page in (self.store_page, self.admin_page):
            with self.subTest(page=page):
                duplicates = [key for key, count in Counter(page.ids).items() if count != 1]
                self.assertEqual(duplicates, [])

    def test_storefront_actions_retain_expected_ids(self):
        needed = {
            "catalog", "categoryFilter", "serviceSearch", "refresh", "status",
            "ordersBtn", "orders", "activityBtn", "activity", "orderDialog",
            "orderForm", "orderTitle", "requirements", "formError", "submitOrder", "cancel"
        }
        self.assertFalse(needed.difference(self.store_page.ids))

    def test_admin_login_and_editors_retain_expected_ids(self):
        needed = {
            "adminAccess", "adminDashboard", "adminLoginFields", "accessStatus",
            "adminPhoneForm", "adminOtpForm", "adminLoginPhone", "adminLoginName",
            "adminLoginCode", "requestAdminCode", "verifyAdminCode", "recheckAdmin",
            "summary", "orders", "details", "packages", "packageForm",
            "packagesRefresh", "filter", "refresh", "packageMessage",
            "slug", "category", "title_ar", "description_ar", "price_sar",
            "delivery_days", "revision_limit", "active", "savePackage", "resetPackage"
        }
        self.assertFalse(needed.difference(self.admin_page.ids))

    def test_all_internal_navigation_anchors_resolve(self):
        for page in (self.store_page, self.admin_page):
            for anchor in page.anchors:
                with self.subTest(anchor=anchor):
                    self.assertIn(anchor, page.ids)

    def test_responsive_styles_are_defined(self):
        for markup in (self.store, self.admin):
            self.assertIn("@media(max-width:", markup)
            self.assertIn("prefers-reduced-motion", markup)
            self.assertIn(":focus-visible", markup)

    def test_store_and_admin_show_explicit_preview_context(self):
        self.assertIn("نسخة تجريبية", self.store)
        self.assertIn("بيئة تجريبية", self.admin)
        self.assertIn("لا توجد معاملات دفع حقيقية", self.store)
        self.assertIn("بدون معاملات دفع حقيقية", self.admin)

    def test_admin_sensitive_ui_is_hidden_before_auth(self):
        self.assertRegex(self.admin, r'<div\s+id="adminDashboard"[^>]*\shidden')
        self.assertRegex(self.admin, r'<div\s+id="adminLoginFields"[^>]*\shidden')

    def test_storefront_has_a_single_primary_title(self):
        self.assertEqual(self.store_page.headings.count("h1"), 1)
        self.assertGreaterEqual(self.store_page.headings.count("h2"), 2)

if __name__ == "__main__":
    unittest.main()
