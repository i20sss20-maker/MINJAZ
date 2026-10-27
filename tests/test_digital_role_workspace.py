"""Fast isolated MINJAZ workspace must be navigable without legacy app load.

This is a preview-only UI; all reads/writes still use role-guarded existing APIs.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
HTML = (ROOT / "public" / "workspace.html").read_text(encoding="utf-8")
JS = (ROOT / "public" / "workspace-v1.js").read_text(encoding="utf-8")
SIGNUP = (ROOT / "public" / "signup.html").read_text(encoding="utf-8")
STORE = (ROOT / "public" / "digital-services.html").read_text(encoding="utf-8")


class RoleWorkspaceTests(unittest.TestCase):
    def test_routes_are_preview_only_with_correct_mime(self):
        self.assertIn("p in ('/workspace','/workspace/')", SERVER)
        self.assertIn("p=='/workspace-v1.js'", SERVER)
        self.assertGreaterEqual(SERVER.count("if APP_ENV!='preview': return self.sendj(404,{'error':'not_found'})"), 3)
        self.assertIn("open(os.path.join(os.path.dirname(HTML_PATH),'workspace.html'),'rb')", SERVER)
        self.assertIn("open(os.path.join(os.path.dirname(HTML_PATH),'workspace-v1.js'),'rb')", SERVER)
        self.assertIn("self._headers(200,'application/javascript; charset=utf-8')", SERVER)

    def test_client_freelancer_admin_ux_present(self):
        for form in ("newTask", "offerForm", "nameForm", "freelancerProfile"):
            self.assertIn('id="'+form+'"', HTML)
        for endpoint in ("/api/v1/me", "/api/v1/tasks", "/api/v1/orders",
                         "/api/v1/notifications?limit=8", "/api/admin/summary",
                         "/api/v1/me/active-role", "/api/v1/freelancer/profile",
                         "/api/v1/legal/documents", "/api/v1/legal/accept",
                         "/api/v1/auth/logout"):
            self.assertIn(endpoint, JS)
        self.assertIn('credentials:"same-origin"', JS)
        self.assertIn("function esc(", JS)

    def test_no_fake_money_or_unprotected_admin_access(self):
        # Do not offer mock payment actions, automatic legal acceptance,
        # or a client-side assertion of admin privilege.
        self.assertNotIn("/pay", JS)
        self.assertNotIn("payment_mode=mock", JS)
        self.assertNotIn("ADMIN_EMAIL", JS)
        self.assertIn('querySelectorAll(\'input[type="checkbox"]:checked\')', JS)
        self.assertIn('missing.some(x=>!checked.includes(x))', JS)
        self.assertIn('const result=await request("/api/admin/summary")', JS)

    def test_signup_and_store_use_fast_paths_not_broken_app_link(self):
        self.assertIn('href="/workspace"', SIGNUP)
        self.assertNotIn('href="/app"', SIGNUP)
        self.assertIn('window.location.assign(backToStore?"/digital-services":"/workspace")', SIGNUP)
        self.assertIn('href="/signup?auth=login&amp;next=digital-services"', STORE)
        self.assertIn("a.href='/signup?auth=login&next=digital-services'", STORE)
        self.assertNotIn('href="/?auth=login&amp;next=digital-services"', STORE)

    def test_website_assets_are_not_in_legacy_shell_or_service_worker(self):
        self.assertIn('src="/workspace-v1.js" defer', HTML)
        self.assertNotIn("public/index.html", HTML)
        self.assertIn("role", JS)
        self.assertIn("AbortController()", JS)
        self.assertIn("idempotency_key:", JS)
        self.assertIn("request(\"/api/v1/auth/logout\"", JS)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable in minimal Docker image")
    def test_javascript_parses(self):
        subprocess.run(["node", "--check", str(ROOT / "public" / "workspace-v1.js")], check=True)


if __name__ == "__main__":
    unittest.main()
