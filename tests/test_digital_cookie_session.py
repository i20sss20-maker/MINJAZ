"""Regression tests for real browser cookie authentication and admin readiness UI.

The session extractor is loaded from its own AST node so these tests never
connect to production or import the server's environment-dependent startup.
"""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_cookie_parser():
    source = (ROOT / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(n for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "session_token_from_headers")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {"re": re, "SESSION_COOKIE_NAME": "minjaz_session"}
    exec(compile(module, str(ROOT / "server.py"), "exec"), namespace)
    return namespace["session_token_from_headers"]


class SessionCookieRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extract = staticmethod(load_cookie_parser())

    def test_cookie_first(self):
        raw = "a" * 64
        self.assertEqual(self.extract({"Cookie": f"minjaz_session={raw}; theme=light"}), (raw, "cookie"))

    def test_cookie_after_another_cookie(self):
        raw = "a" * 64
        for cookie in (
            f"theme=light; minjaz_session={raw}",
            f"theme=light;minjaz_session={raw}",
            f"first=1; second=2;   minjaz_session={raw}; third=3",
            f"first=1;\tminjaz_session={raw}",
        ):
            with self.subTest(cookie=cookie[:35]):
                self.assertEqual(self.extract({"Cookie": cookie}), (raw, "cookie"))

    def test_rejects_lookalike_cookie_name_and_bad_value(self):
        for cookie in ("other_minjaz_session=" + "a" * 64,
                       "minjaz_session=" + "x" * 64,
                       "minjaz_session=" + "a" * 63):
            self.assertEqual(self.extract({"Cookie": cookie}), ("", ""))

    def test_authorization_header_still_takes_precedence(self):
        raw = "b" * 64
        self.assertEqual(
            self.extract({"Cookie": "minjaz_session=" + "a" * 64,
                          "Authorization": "Bearer " + raw}),
            (raw, "bearer"),
        )

    def test_admin_status_contract_matches_api_response(self):
        admin = (ROOT / "public" / "digital-services-admin.html").read_text(encoding="utf-8")
        server = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn("'admin_configured':", server)
        self.assertIn("status.admin_configured", admin)
        self.assertNotIn("status.admin_email_configured", admin)
        self.assertIn("[hidden]{display:none!important}", admin)


if __name__ == "__main__":
    unittest.main()
