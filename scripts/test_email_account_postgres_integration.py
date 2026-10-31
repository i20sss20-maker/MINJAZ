#!/usr/bin/env python3
"""Full email account life cycle against isolated local PostgreSQL only.

No email is sent. A mocked mailbox captures verification and password reset
URLs, ensuring live email transport configuration remains untouched.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import psycopg2
from minjaz_account_auth import (
    register, consume_email_link, login, request_password_reset,
    reset_password, resend_verification
)

URL=os.getenv("DIGITAL_TEST_DATABASE_URL","")
SECRET="ci-local-email-verification-secret-not-real-0e75cc8a"
CAPTURED=[]

def connect():
    parsed=urlparse(URL)
    if (os.getenv("CI","").lower()!="true" or parsed.scheme not in ("postgresql","postgres")
        or parsed.hostname not in ("127.0.0.1","localhost") or parsed.port!=5432
        or parsed.path!="/digital_test" or parsed.username!="postgres"):
        raise RuntimeError("Refuse nonlocal/production database access")
    return psycopg2.connect(URL,connect_timeout=5)

def send_mock(email,purpose,token):
    CAPTURED.append((email,purpose,token))

def check(ok,message):
    if not ok:raise AssertionError(message)

def setup():
    schema="""
    CREATE TABLE users (
      id BIGSERIAL PRIMARY KEY,
      phone TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL DEFAULT 'مستخدم',
      role TEXT NOT NULL CHECK(role IN ('client','freelancer','admin')),
      is_verified BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      deleted_at TIMESTAMPTZ
    );
    CREATE TABLE user_roles (
      user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
      role TEXT NOT NULL CHECK(role IN ('client','freelancer','admin')),
      enabled BOOLEAN DEFAULT TRUE,
      PRIMARY KEY (user_id,role)
    );
    CREATE TABLE freelancer_profiles (
      user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE sessions (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      token_hash TEXT UNIQUE NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    with connect() as db:
        with db.cursor() as cur:
            cur.execute(schema)
        for name in ("007_account_security.sql","034_verified_email_login.sql",
                     "035_verified_password_accounts.sql"):
            with db.cursor() as cur:
                cur.execute((ROOT/"database"/"migrations"/name).read_text(encoding="utf8"))
            print("PASS applied "+name)

def run():
    setup()
    base={"name":"عميل تجريبي","phone":"0512345678","email":"client@example.com",
          "password":"ClientSecurePass2026!","role":"client"}
    status,result=register(base,connect,SECRET,send_mock,ready=True)
    check(status==201 and result["email_verification_required"],"Registration not created")
    check(CAPTURED[-1][0:2]==("client@example.com","verify"),"Wrong activation email")
    activation=CAPTURED[-1][2]
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("SELECT email_verified_at,is_verified,password_hash,phone FROM users WHERE email=%s",
                        ("client@example.com",))
            verified,is_verified,password_hash,phone=cur.fetchone()
            check(verified is None and not is_verified and password_hash.startswith("scrypt$")
                  and phone=="+966512345678","Account fields not captured or improperly verified")
            cur.execute("SELECT COUNT(*) FROM sessions")
            check(cur.fetchone()[0]==0,"Registration bypassed email activation")
    code,data=login({"email":base["email"],"password":base["password"]},
                    connect,SECRET,"",7,"CI-integration","127.0.0.1")
    check(code==403 and data["error"]=="email_not_verified",
          "Unverified account got access")
    status,result=consume_email_link({"token":activation},connect,SECRET,"")
    check(status==200 and result["verified"],"Activation link could not verify mailbox")
    code,_=consume_email_link({"token":activation},connect,SECRET,"")
    check(code==400,"Activation was not single-use")
    code,data=login({"email":base["email"],"password":base["password"]},
                    connect,SECRET,"",7,"CI-integration","127.0.0.1")
    check(code==200 and data["user"]["role"]=="client"
          and len(data["session_raw"])==64,"Verified customer cannot log in")
    raw=data["session_raw"]
    code,_=login({"email":base["email"],"password":"wrongpass1234"},connect,
                 SECRET,"",7,"CI-integration","127.0.0.1")
    check(code==401,"Incorrect password accepted")
    code,_=register(base,connect,SECRET,send_mock,ready=True)
    check(code==409,"Duplicate registration accepted")
    print("PASS signup blocked until email activation, single-use link, correct login and duplicate")

    code,_=request_password_reset({"email":base["email"]},connect,SECRET,send_mock,ready=True)
    check(code==200 and CAPTURED[-1][1]=="reset","Password recovery email not sent")
    recovery=CAPTURED[-1][2]
    code,_=reset_password({"token":recovery,"password":"FreshStrong2026!"},
                         connect,SECRET)
    check(code==200,"Password reset failed")
    code,_=reset_password({"token":recovery,"password":"FreshStrong2026!"},
                         connect,SECRET)
    check(code==400,"Recovery token incorrectly reusable")
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("SELECT revoked_at FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=%s)",(base["email"],))
            sessions=cur.fetchall()
            check(sessions and all(row[0] is not None for row in sessions),
                  "Reset did not revoke existing sessions")
    check(login({"email":base["email"],"password":base["password"]},
                connect,SECRET,"",7,"CI","127.0.0.1")[0]==401,
          "Old password remained valid")
    check(login({"email":base["email"],"password":"FreshStrong2026!"},
                connect,SECRET,"",7,"CI","127.0.0.1")[0]==200,
          "New password invalid")
    print("PASS password reset, revoke sessions, prevent token reuse and old password login")

    freelance={"name":"مستقل تجريبي","phone":"0512345679",
               "email":"freelancer@example.com","password":"FreelanceSecure2026!",
               "role":"freelancer"}
    code,_=register(freelance,connect,SECRET,send_mock,ready=True)
    check(code==201,"Freelancer registration unavailable")
    code,_=consume_email_link({"token":CAPTURED[-1][2]},connect,SECRET,"")
    check(code==200,"Freelancer activation failed")
    code,data=login({"email":freelance["email"],"password":freelance["password"]},
                    connect,SECRET,"",7,"CI","127.0.0.1")
    check(code==200 and data["user"]["role"]=="freelancer","Freelancer login failed")
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM freelancer_profiles WHERE user_id=%s",(data["user"]["id"],))
            check(cur.fetchone()[0]==1,"Freelancer profile missing")
    print("PASS freelancer activation, role and profile")

    administrative={"name":"مدير تجريبي","phone":"0512345690","email":"admin@example.com",
                    "password":"AdminSecure2026!","role":"client"}
    code,_=register(administrative,connect,SECRET,send_mock,ready=True)
    check(code==201,"Admin mailbox registration failed")
    code,_=consume_email_link({"token":CAPTURED[-1][2]},connect,SECRET,
                              "admin@example.com")
    check(code==200,"Admin mailbox activation failed")
    code,account=login({"email":administrative["email"],"password":administrative["password"]},
                       connect,SECRET,"admin@example.com",7,"CI","127.0.0.1")
    check(code==200 and account["user"]["role"]=="admin",
          "Verified admin mailbox not granted expected permission")
    code,_=login({"email":administrative["email"],"password":administrative["password"]},
                 connect,SECRET,"someoneelse@example.com",7,"CI","127.0.0.1")
    check(code==403,"Admin logged in after configured mailbox changed")
    print("PASS reserved admin email scope")

    code,_=request_password_reset({"email":"missing@example.com"},connect,SECRET,
                                  send_mock,ready=True)
    check(code==200 and CAPTURED[-1][0]!="missing@example.com",
          "Missing account enumeration or spurious email")
    print("PASS password reset anti-enumeration")
    print("PASS COMPLETE: Verified MINJAZ registration, login, recovery and roles")

if __name__=="__main__":
    run()
