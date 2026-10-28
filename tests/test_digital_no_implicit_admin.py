"""Regression: proving email ownership cannot elevate MINJAZ privileges.

Only the explicit owner-admin claim challenge can set administrator rights.
Tests run without any real mailbox, external database or user credentials.
"""
import unittest
from pathlib import Path
from minjaz_account_auth import consume_email_link,token_digest

SECRET="not-a-production-secret-"*4
TOKEN="X"*43
OWNER="owner@example.invalid"


class VerifyCursor:
    def __init__(self,record):
        self.record=record
        self.statements=[]
        self.pending=None
    def __enter__(self):
        return self
    def __exit__(self,*_):
        return False
    def execute(self,sql,args=()):
        self.statements.append((sql,args))
        if "SELECT a.id,a.user_id,a.action" in sql:
            self.pending=self.record
        else:
            self.pending=None
    def fetchone(self):
        return self.pending


class VerifyConnection:
    def __init__(self,record):
        self.cur=VerifyCursor(record)
        self.commits=0
        self.rollbacks=0
        self.closed=False
    def cursor(self,**kwargs):
        assert "cursor_factory" in kwargs
        return self.cur
    def commit(self):
        self.commits+=1
    def rollback(self):
        self.rollbacks+=1
    def close(self):
        self.closed=True


class EmailNeverElevatesRole(unittest.TestCase):
    def test_owner_email_verification_does_not_change_role(self):
        db=VerifyConnection({"id":11,"user_id":7,"action":"verify",
                             "email":OWNER,"role":"client","expired":False})
        code,data=consume_email_link({"token":TOKEN},lambda:db,SECRET,OWNER)
        self.assertEqual((code,data),(200,{"verified":True}))
        self.assertEqual(db.commits,1)
        self.assertTrue(db.closed)
        self.assertTrue(any("email_verified_at=now()" in sql for sql,_ in db.cur.statements))
        self.assertTrue(any("used_at=now()" in sql for sql,_ in db.cur.statements))
        for statement,_ in db.cur.statements:
            self.assertNotIn("role='admin'",statement)
            self.assertNotIn("INTO user_roles",statement)

    def test_admin_email_with_freelancer_role_stays_freelancer(self):
        db=VerifyConnection({"id":12,"user_id":8,"action":"verify",
                             "email":OWNER,"role":"freelancer","expired":False})
        code,data=consume_email_link({"token":TOKEN},lambda:db,SECRET,OWNER)
        self.assertEqual(code,200)
        self.assertTrue(data["verified"])
        self.assertEqual(db.commits,1)
        self.assertFalse(any("user_roles" in sql.lower() or "role='admin'" in sql.lower()
                             for sql,_ in db.cur.statements))

    def test_expired_token_does_not_verify_or_promote(self):
        db=VerifyConnection({"id":13,"user_id":9,"action":"verify",
                             "email":OWNER,"role":"client","expired":True})
        code,data=consume_email_link({"token":TOKEN},lambda:db,SECRET,OWNER)
        self.assertEqual(code,410)
        self.assertEqual(data["error"],"email_link_expired")
        self.assertEqual(db.commits,0)
        self.assertFalse(any("UPDATE users" in sql for sql,_ in db.cur.statements))

    def test_unknown_token_never_promotes(self):
        db=VerifyConnection(None)
        code,data=consume_email_link({"token":TOKEN},lambda:db,SECRET,OWNER)
        self.assertEqual(code,400)
        self.assertEqual(db.commits,0)
        self.assertEqual(data["error"],"invalid_or_used_link")

    def test_token_tied_to_verify_action_and_digest(self):
        db=VerifyConnection({"id":14,"user_id":7,"action":"verify",
                             "email":OWNER,"role":"client","expired":False})
        consume_email_link({"token":TOKEN},lambda:db,SECRET,OWNER)
        selects=[(sql,args) for sql,args in db.cur.statements if "SELECT a.id" in sql]
        self.assertEqual(len(selects),1)
        self.assertIn("a.action='verify'",selects[0][0])
        self.assertIn("a.used_at IS NULL",selects[0][0])
        self.assertEqual(selects[0][1],(token_digest(SECRET,TOKEN),))

    def test_role_elevation_is_implemented_only_in_explicit_admin_claim(self):
        root=Path(__file__).resolve().parents[1]
        auth=(root/"minjaz_account_auth.py").read_text(encoding="utf-8")
        claim=(root/"minjaz_admin_claim.py").read_text(encoding="utf-8")
        verify=auth[auth.index("def consume_email_link("):auth.index("def resend_verification(")]
        self.assertNotIn("role='admin'",verify)
        self.assertNotIn("INTO user_roles",verify)
        self.assertIn("UPDATE users SET role='admin'",claim)
        self.assertIn("verify_password(password",claim)
        self.assertIn("token_hash=%s",claim)
        self.assertIn("email_verified_at IS NOT NULL",claim)


if __name__=="__main__":
    unittest.main()
