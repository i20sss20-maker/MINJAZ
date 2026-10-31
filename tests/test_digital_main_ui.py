"""Main MINJAZ UI design regression checks for every application role.

Read-only checks: customer, freelancer and administration share one native
application document and an independently served versioned stylesheet.
"""
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "public" / "index.html"
STYLE = ROOT / "public" / "minjaz-unified-ui-v1.css"

class PageIds(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.ids = []
        self.feed(markup)
    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("id"):
            self.ids.append(data["id"])

class UnifiedMainUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = UI.read_text("utf-8")
        cls.css = STYLE.read_text("utf-8")
        cls.server = (ROOT / "server.py").read_text("utf-8")

    def test_all_three_roles_and_functional_page_routes_remain(self):
        for role in ("client", "freelancer", "admin"):
            self.assertIn(role, self.html)
        for page in ("home", "tasks", "orders", "notifications", "freelancers", "team", "account", "admin"):
            self.assertIn(f'id="{page}" class="page', self.html)

    def test_essential_login_and_navigation_controls_remain(self):
        ids = PageIds(self.html).ids
        for required in ("auth", "app", "roleClient", "roleFreelancer", "loginName",
                         "loginPhone", "otpBox", "sendOtpBtn", "verifyOtpBtn",
                         "sideNav", "mobileNav", "pageTitle", "pageSub",
                         "modalOverlay", "modal", "mainContent"):
            self.assertIn(required, ids)

    def test_new_stylesheet_linked_at_tail_and_served(self):
        self.assertIn('id="minjazUnifiedDesign"', self.html)
        self.assertIn('href="/minjaz-unified-ui-v1.css"', self.html)
        self.assertIn("p=='/minjaz-unified-ui-v1.css'", self.server)
        self.assertIn("'text/css; charset=utf-8'", self.server)
        self.assertGreater(UI.stat().st_size, 290000)
        self.assertGreater(STYLE.stat().st_size, 24000)

    def test_role_specific_home_actions_exist(self):
        self.assertIn("روابط سريعة للعميل", self.html)
        self.assertIn("روابط سريعة للمستقل", self.html)
        self.assertIn("dataset.minjazRole=me.user.role", self.html)
        self.assertIn("dataset.minjazPage=id", self.html)
        for action in ('newTaskModal()', "go('tasks')", "go('orders')", "go('account')"):
            self.assertIn(action, self.html)

    def test_premium_shared_components_cover_customer_freelancer_admin(self):
        for selector in (".shell{", ".side{", ".topbar{", ".hero{", ".rowCard{",
                         ".orderStepper{", ".chat{", ".auth{", ".modal{",
                         ".kpiGrid{", ".roleQuickLinks{", ".workCenterHeadV23",
                         ".clientProjectsHeadV24", ".dailyHeroV26",
                         ".notifGroupV27", ".filesHeroV30", ".inboxHeroV29"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css)

    def test_mobile_dark_mode_and_accessibility(self):
        for selector in ("@media(max-width:980px)", "@media(max-width:720px)",
                         "@media(max-width:430px)", 'html[data-theme="dark"]',
                         "prefers-reduced-motion", ":focus-visible"):
            self.assertIn(selector, self.css)
        self.assertEqual(self.css.count("{"), self.css.count("}"))

    def test_preserve_existing_api_and_workflows(self):
        for route in ("/api/v1/tasks", "/api/v1/orders", "/api/v1/me",
                      "/api/admin/summary", "/api/v1/team"):
            self.assertIn(route, self.html)
        for function in ("newTaskModal", "renderClientHome", "renderFreelancerHome",
                         "renderAdmin", "renderOrders", "renderAccount",
                         "renderTasks", "orderModal", "buildNav"):
            self.assertIn("function " + function + "(", self.html)

if __name__ == "__main__":
    unittest.main()
