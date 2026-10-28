"""Secure owner-admin enrollment regression coverage. No real emails are sent."""
import os
import unittest
from unittest.mock import patch

import minjaz_admin_claim as admin
from minjaz_account_auth import token_digest

PASSWORD = "Valid-test-2026%"
SECRET = "x" * 64
OWNER = "owner@example.com"
TOKEN = "L" * 43


class FakeCursor:
    def __init__(self, mode, owner=OWNER):
        self.mode = mode
        self.owner = owner
        self.statements = []
        self.last = None
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if self.mode == "request":
            if "SELECT email,password_hash" in sql:
                self.last = {
                    "email": self.owner, "password_hash": "stored",
                    "email_verified_at": "2026-10-28", "role": "client"
                }
            elif "count(*)::int" in sql:
                self.last = {"n": 0, "elapsed": None}
            else:
                self.last = None
        else:
            if "SELECT id,email,password_hash" in sql:
                self.last = {
                    "id": 7, "email": self.owner, "password_hash": "stored",
                    "email_verified_at": "2026-10-28", "role": "client"
                }
            elif "SELECT id,(expires_at" in sql:
                self.last = {"id": 90, "expired": False}
            else:
                self.last = None
        self.rowcount = 1

    def fetchone(self):
        return self.last


class FakeConnection:
    def __init__(self, mode, owner=OWNER):
        self.cursor_value = FakeCursor(mode, owner)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, **kwargs):
        assert "cursor_factory" in kwargs
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class OwnerClaimTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"APP_ENV": "preview"}, clear=False)
        self.env.start()
        self.cfg = patch.object(admin, "secure_config", return_value=True)
        self.cfg.start()

    def tearDown(self):
        self.cfg.stop()
        self.env.stop()

    def test_not_configured_owner_never_opens_database(self):
        code, result = admin.request_owner_claim(
            7, PASSWORD, lambda: self.fail("DB should not open"),
            SECRET, "")
        self.assertEqual(code, 503)
        self.assertEqual(result["error"], "admin_setup_unavailable")

    def test_non_preview_cannot_claim_admin(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            code, _ = admin.confirm_owner_claim(
                7, 15, PASSWORD, TOKEN,
                lambda: self.fail("DB should not open"), SECRET, OWNER)
        self.assertEqual(code, 503)

    def test_invalid_token_does_not_open_database(self):
        code, result = admin.confirm_owner_claim(
            7, 15, PASSWORD, "bad", lambda: self.fail("no DB"),
            SECRET, OWNER)
        self.assertEqual(code, 400)
        self.assertEqual(result["error"], "invalid_token")

    def test_owner_request_requires_password_and_exact_verified_email(self):
        db = FakeConnection("request", "not-owner@example.com")
        code, result = admin.request_owner_claim(7, PASSWORD, lambda: db,
            SECRET, OWNER)
        self.assertEqual(code, 403)
        self.assertEqual(result["error"], "admin_claim_not_allowed")
        self.assertEqual(db.commits, 0)
        self.assertTrue(db.closed)

    def test_request_sends_single_use_token_to_configured_email(self):
        db = FakeConnection("request")
        mail = []
        with patch.object(admin, "verify_password", return_value=True), \
             patch.object(admin, "new_action", return_value=TOKEN):
            code, data = admin.request_owner_claim(
                7, PASSWORD, lambda: db, SECRET, OWNER,
                deliver=lambda email, action, raw: mail.append((email, action, raw)))
        self.assertEqual(code, 200)
        self.assertTrue(data["email_confirmation_required"])
        self.assertEqual(data["expires_in_seconds"], 900)
        self.assertEqual(mail, [(OWNER, "admin_claim", TOKEN)])
        self.assertEqual(db.commits, 1)
        self.assertTrue(db.closed)

    def test_confirm_rechecks_password_and_token_then_revokes_other_sessions(self):
        db = FakeConnection("confirm")
        with patch.object(admin, "verify_password", return_value=True):
            code, result = admin.confirm_owner_claim(
                7, 22, PASSWORD, TOKEN, lambda: db, SECRET, OWNER)
        self.assertEqual(code, 200)
        self.assertTrue(result["admin_activated"])
        self.assertEqual(db.commits, 1)
        statements = db.cursor_value.statements
        self.assertTrue(any("UPDATE users SET role='admin'" in sql for sql, _ in statements))
        self.assertTrue(any("UPDATE user_roles SET enabled=false" in sql for sql, _ in statements))
        self.assertTrue(any("action='admin_claim' AND token_hash=%s" in sql and
                            params == (7, token_digest(SECRET, TOKEN))
                            for sql, params in statements))
        self.assertTrue(any("UPDATE sessions SET revoked_at=now()" in sql
                            and params == (7, 22) for sql, params in statements))
        self.assertTrue(db.closed)

    def test_wrong_password_never_promotes(self):
        db = FakeConnection("confirm")
        with patch.object(admin, "verify_password", return_value=False):
            code, result = admin.confirm_owner_claim(
                7, 22, PASSWORD, TOKEN, lambda: db, SECRET, OWNER)
        self.assertEqual(code, 403)
        self.assertEqual(result["error"], "invalid_credentials")
        self.assertFalse(any("UPDATE users" in x for x, _ in db.cursor_value.statements))
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
