"""Unit tests for secure, single-use MINJAZ email OTP and provider readiness."""
import unittest

from minjaz_email_auth import (
    code_digest, email_delivery_config, normalize_email, request_email_otp,
    verify_email_otp,
)

SECRET = "test-not-production-secret-" + "x" * 48

class NoDB:
    def __call__(self):
        raise AssertionError("invalid auth input must not query a database")

class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.row = None
        self.rows = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        self.db.sql.append((q, params))
        self.row = None
        if "SELECT count(*)::int AS n" in q:
            self.row = {"n": len(self.db.challenges), "seconds": 90 if self.db.challenges else None}
        elif "INSERT INTO email_login_challenges" in q:
            cid, email, role, digest = params
            self.db.challenges[cid] = {
                "id":len(self.db.challenges)+1, "email":email,"requested_role":role,
                "code_hash":digest,"verified_at":None,"expired":False,"attempts":0,
            }
        elif "DELETE FROM email_login_challenges" in q:
            self.db.challenges.pop(params[0], None)
        elif "SELECT id,email,requested_role,code_hash" in q:
            self.row = self.db.challenges.get(params[0])
        elif "UPDATE email_login_challenges SET attempts" in q:
            for challenge in self.db.challenges.values():
                if challenge["id"] == params[0]:
                    challenge["attempts"] += 1
        elif "UPDATE email_login_challenges SET verified_at" in q:
            for challenge in self.db.challenges.values():
                if challenge["id"] == params[0]:
                    challenge["verified_at"] = "now"
        elif "SELECT id,role FROM users WHERE email" in q:
            user = self.db.users.get(params[0])
            self.row = {"id":user["id"],"role":user["role"]} if user else None
        elif "INSERT INTO users(email,name,role,is_verified)" in q:
            email,name,role = params
            self.db.users[email]={"id":101+len(self.db.users),"name":name,"role":role}
            self.row={"id":self.db.users[email]["id"]}
        elif "UPDATE users SET name" in q:
            name,role,uid = params
            for user in self.db.users.values():
                if user["id"] == uid:
                    user["name"] = name
                    user["role"] = role
        elif "INSERT INTO user_roles" in q:
            self.db.roles.add((params[0],params[1]))
        elif "INSERT INTO freelancer_profiles" in q:
            self.db.freelancers.add(params[0])
        elif "INSERT INTO sessions" in q:
            self.db.session_count+=1
            self.row={"id":self.db.session_count}
        elif "SELECT role FROM user_roles" in q:
            self.rows=[{"role":role} for uid,role in self.db.roles if uid==params[0]]
        else:
            raise AssertionError("unhandled SQL: "+q)
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows

class FakeDB:
    def __init__(self):
        self.challenges={}
        self.users={}
        self.roles=set()
        self.freelancers=set()
        self.session_count=0
        self.sql=[]
        self.commits=0
        self.rollbacks=0
        self.closes=0
    def __call__(self):
        return self
    def cursor(self, **kwargs):
        return FakeCursor(self)
    def commit(self):
        self.commits+=1
    def rollback(self):
        self.rollbacks+=1
    def close(self):
        self.closes+=1

class EmailAuthTests(unittest.TestCase):
    def request(self, db, email="client@example.com", role="client", delivery=None):
        codes = []
        def send(addr, code):
            codes.append((addr, code))
            if delivery:
                delivery(addr,code)
        result = request_email_otp({"email":email,"role":role},db,SECRET,send)
        return result,codes
    def verify(self, db, challenge_id, code, admin_email="", override=None):
        return verify_email_otp(
            {"challenge_id":challenge_id,"code":code,"name":"مستخدم تجريبي",
             "role":override or "client"},
            db,SECRET,admin_email,True,30,"Unit-Test-Browser","127.0.0.1",
        )

    def test_email_normalization_and_validation(self):
        self.assertEqual(normalize_email("  UsEr+Test@Example.Com  "),"user+test@example.com")
        for value in (None,123,"not-email","a@localhost","a@@b.com",
                      "a..b@example.com","a@example.com\nCc:intruder@example.com",
                      "x" * 70+"@example.com"):
            with self.subTest(value=value):
                self.assertEqual(normalize_email(value),"")

    def test_resend_configuration_requires_sender_key_and_long_secret(self):
        good={"EMAIL_MODE":"resend","EMAIL_FROM":"auth@example.com",
              "RESEND_API_KEY":"re_example_test","AUTH_SECRET":SECRET}
        self.assertTrue(email_delivery_config(good)["enabled"])
        self.assertFalse(email_delivery_config({**good,"AUTH_SECRET":"dev-secret-change-me"})["enabled"])
        self.assertFalse(email_delivery_config({**good,"RESEND_API_KEY":""})["enabled"])

    def test_smtp_configuration_requires_secure_transport_and_password(self):
        env={"EMAIL_MODE":"smtp","EMAIL_FROM":"auth@example.com",
             "SMTP_HOST":"smtp.example.com","SMTP_PORT":"465",
             "SMTP_USERNAME":"auth@example.com","SMTP_PASSWORD":"app-password",
             "AUTH_SECRET":SECRET}
        self.assertTrue(email_delivery_config(env)["enabled"])
        self.assertFalse(email_delivery_config({**env,"SMTP_PORT":"25"})["enabled"])
        self.assertFalse(email_delivery_config({**env,"SMTP_PASSWORD":""})["enabled"])

    def test_disabled_email_does_not_create_otp(self):
        status,data=request_email_otp({"email":"person@example.com","role":"client"},
                NoDB(),SECRET,lambda *args:None,config_ready=False)
        self.assertEqual(status,503)
        self.assertEqual(data["error"],"email_not_configured")

    def test_invalid_email_role_or_source_throttled(self):
        for body in ({"email":"invalid","role":"client"},
                     {"email":"valid@example.com","role":"admin"},
                     {"email":"valid@example.com","role":"contractor"},[]):
            with self.subTest(body=body):
                code,_=request_email_otp(body,NoDB(),SECRET,lambda *_:None)
                self.assertEqual(code,400)
        code,_=request_email_otp({"email":"a@example.com","role":"client"},
               NoDB(),SECRET,lambda *_:None,ip_allowed=False)
        self.assertEqual(code,429)

    def test_request_generates_random_six_digit_code_never_returns_code(self):
        db=FakeDB()
        (status,data), sent=self.request(db)
        self.assertEqual(status,201)
        self.assertEqual(data["delivery"],"email")
        self.assertEqual(len(sent),1)
        self.assertRegex(sent[0][1],r"^[0-9]{6}$")
        self.assertNotIn("code",data)
        self.assertEqual(data["code_length"],6)
        self.assertEqual(len(db.challenges),1)

    def test_delivery_failure_never_issues_login_challenge(self):
        db=FakeDB()
        def failed_sender(*args):
            raise ConnectionError("smtp unavailable")
        (status,data),sent=self.request(db,delivery=failed_sender)
        self.assertEqual(status,502)
        self.assertEqual(db.challenges,{})
        self.assertEqual(db.session_count,0)

    def test_wrong_code_and_one_time_success(self):
        db=FakeDB()
        (_,data),sent=self.request(db)
        challenge=data["challenge_id"]
        status,_=self.verify(db,challenge,"000000" if sent[0][1]!="000000" else "999999")
        self.assertEqual(status,401)
        self.assertEqual(db.challenges[challenge]["attempts"],1)
        status,result=self.verify(db,challenge,sent[0][1])
        self.assertEqual(status,200)
        self.assertEqual(result["user"]["role"],"client")
        self.assertTrue(result["session_raw"])
        self.assertEqual(db.session_count,1)
        self.assertEqual(self.verify(db,challenge,sent[0][1])[0],409)

    def test_expired_challenge_and_five_attempt_cap(self):
        db=FakeDB()
        (_,data),sent=self.request(db)
        cid=data["challenge_id"]
        db.challenges[cid]["expired"]=True
        self.assertEqual(self.verify(db,cid,sent[0][1])[0],410)
        db.challenges[cid]["expired"]=False
        db.challenges[cid]["attempts"]=5
        self.assertEqual(self.verify(db,cid,sent[0][1])[0],429)

    def test_role_fixed_at_email_request_even_if_verify_payload_changes(self):
        db=FakeDB()
        (_,data),sent=self.request(db,role="freelancer")
        code,body=self.verify(db,data["challenge_id"],sent[0][1],override="admin")
        self.assertEqual(code,200)
        self.assertEqual(body["user"]["role"],"freelancer")
        self.assertIn(body["user"]["id"],db.freelancers)

    def test_admin_only_verified_configured_mailbox(self):
        db=FakeDB()
        (_,data),sent=self.request(db,email="owner@example.com")
        code,body=self.verify(db,data["challenge_id"],sent[0][1],admin_email="owner@example.com")
        self.assertEqual(code,200)
        self.assertEqual(body["user"]["role"],"admin")
        self.assertIn("admin",body["roles"])

    def test_non_admin_mailbox_never_receives_admin(self):
        db=FakeDB()
        (_,data),sent=self.request(db,email="intruder@example.com")
        code,body=self.verify(db,data["challenge_id"],sent[0][1],admin_email="owner@example.com")
        self.assertEqual(code,200)
        self.assertNotEqual(body["user"]["role"],"admin")

    def test_verified_admin_cannot_continue_after_admin_email_removed(self):
        db=FakeDB()
        (_,data),sent=self.request(db,email="owner@example.com")
        self.assertEqual(self.verify(db,data["challenge_id"],sent[0][1],
                                     admin_email="owner@example.com")[0],200)
        (_,data2),sent2=self.request(db,email="owner@example.com")
        status,body=self.verify(db,data2["challenge_id"],sent2[0][1],admin_email="")
        self.assertEqual(status,403)
        self.assertEqual(body["error"],"admin_email_mismatch")

    def test_reject_invalid_challenge_format_without_database(self):
        code,body=verify_email_otp(
            {"challenge_id":"bad","code":"123456","name":"صالح"},
            NoDB(),SECRET,"",True,30,"Browser","")
        self.assertEqual(code,400)
        self.assertEqual(body["error"],"invalid_code")
if __name__=="__main__":
    unittest.main()
