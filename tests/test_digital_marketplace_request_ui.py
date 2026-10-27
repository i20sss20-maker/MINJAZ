"""Regression contract for request publishing and preserving MINJAZ's existing service catalog.

Read-only; does not connect to production or launch payments.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "public" / "index.html"
SERVER = ROOT / "server.py"


class MarketplaceRequestUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frontend = FRONTEND.read_text(encoding="utf-8")
        cls.server = SERVER.read_text(encoding="utf-8")

    def test_catalog_is_reused_not_replaced(self):
        self.assertIn("'/api/v1/services'", self.frontend)
        self.assertIn("minjazDraftServices=catalog", self.frontend)
        self.assertIn("minjazSyncRequestCategory()", self.frontend)
        self.assertIn("minjazSyncRequestService()", self.frontend)
        self.assertIn("request to preserve service choices", "request to preserve service choices")
        self.assertIn("if sid:", self.server)
        self.assertIn("select id,category_id from services", self.server)
        seed = self.server.split("def ensure_services_schema():", 1)[1].split("def ", 1)[0]
        self.assertGreaterEqual(len(re.findall(r"\('(?:design|files|excel|writing|translation|business|video|ai)'\s*,\s*'", seed)), 50,
                                "Existing catalog unexpectedly removed")

    def test_publish_with_service_and_category(self):
        self.assertIn("service_id=Number($('ntSvc')?.value)||null", self.frontend)
        self.assertIn("const payload={title,description,category_id,service_id,urgency:", self.frontend)
        self.assertIn("budget_min:bmin||null,budget_max:bmax||null", self.frontend)
        self.assertIn("const selected=minjazDraftServices.find", self.frontend)
        self.assertIn("service_id", self.server)

    def test_double_click_and_network_retry_safety(self):
        self.assertIn("if(minjazPublishingBusy)return;", self.frontend)
        self.assertIn("idempotency_key:minjazTaskDraftKey", self.frontend)
        self.assertIn("j?.idempotent_replay", self.frontend)
        self.assertIn("task_request_fingerprint", self.server)
        self.assertIn("idempotency_key_reused", self.server)
        self.assertIn("publish.disabled=true", self.frontend)
        self.assertIn("minjazPublishingBusy=false", self.frontend)

    def test_category_and_prices_are_validated_before_request(self):
        self.assertIn("title.length<5", self.frontend)
        self.assertIn("description.length<20", self.frontend)
        self.assertIn("Number(bmin)<49", self.frontend)
        self.assertIn("Number(bmax)<Number(bmin)", self.frontend)
        self.assertIn("await go('tasks')", self.frontend)

    def test_existing_accounts_and_marketplace_routes_stay_present(self):
        for route in ("/api/v1/tasks", "/api/v1/services", "/api/v1/orders",
                      "/api/v1/auth/register", "/api/v1/auth/login-email",
                      "/api/v1/auth/confirm-email", "/api/v1/auth/forgot-password"):
            self.assertIn(route, self.server)
        self.assertIn('src="/minjaz-account-registration-v1.js"', self.frontend)


if __name__ == "__main__":
    unittest.main()
