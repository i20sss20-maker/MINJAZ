"""Resend API clients must not use default Python-urllib User-Agent."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ResendHeaderTests(unittest.TestCase):
    def test_all_resend_callers_have_explicit_http_headers(self):
        for path in ("minjaz_email_auth.py",
                     "minjaz_account_auth.py",
                     "scripts/probe_minjaz_resend_sender.py"):
            with self.subTest(module=path):
                source=(ROOT/path).read_text("utf-8")
                self.assertIn('"User-Agent": "Mozilla/5.0 (compatible; MINJAZ-Mailer/1.0)"',source)
                self.assertIn('"Accept": "application/json"',source)
                self.assertIn('"Content-Type": "application/json"',source)

if __name__=="__main__":
    unittest.main()
