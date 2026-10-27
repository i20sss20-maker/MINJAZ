#!/usr/bin/env python3
"""Full MINJAZ verified account integration on isolated CI PostgreSQL.

Never opens a Railway database or contacts an external mail provider.
Only accepts 127.0.0.1:5432/account_test when CI=true.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import psycopg2
import psycopg2.extras

from minjaz_account_auth import (
    register,consume_email_link,resend_verification,login,
    request_password_reset,reset_password
)
from minjaz_email_auth import normalize_email

DATABASE=os.getenv("MINJAZ_ACCOUNT_TEST_DATABASE_URL","")
SECRET="this-is-only-for-ephemeral-ci-auth-fixtures-not-real"
MAILED=[]

def connect():
    p=urlparse(DATABASE)
    if (os.getenv("CI","").lower()!="true" or p.scheme not in ("postgresql","postgres")
        or p.hostname not in ("localhost","127.0.0.1") or p.port!=5432
        or p.path!="/account_test" or p.username!="postgres"):
        raise RuntimeError("Auth integration test refuses any nonlocal/real database")
    return psycopg2.connect(DATABASE,connect_timeout=5)

def send(address,action,raw):
    MAILED.append((address,action,raw))

def assert_true(condition,label):
    if not condition:raise AssertionError(label)

def make_database():
    database_admin="postgresql://postgres:postgres@127.0.0.1:5432/postgres"
    p=urlparse(DATABASE)
    if os.getenv("CI")!="true" or p.path!="/account_test":
        raise RuntimeError("Unsafe database bootstrap")
    admin=psycopg2.connect(database_admin);admin.autocommit=True
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname='account_test'")
        if not cur.fetchone():cur.execute("CREATE DATABASE account_test")
    admin.close()
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("""CREATE TABLE users(
              id BIGSERIAL PRIMARY KEY,phone TEXT NOT NULL UNIQUE,name TEXT NOT NULL,
              role TEXT NOT NULL,is_verified BOOLEAN NOT NULL DEFAULT false,
              deleted_at TIMESTAMPTZ)""")
            cur.execute("""CREATE TABLE user_roles(
              user_id BIGINT NOT NULL REFERENCES users(id),role TEXT NOT NULL,
              enabled BOOLEAN NOT NULL DEFAULT true,
              UNIQUE(user_id,role))""")
            cur.execute("""CREATE TABLE freelancer_profiles(
              user_id BIGINT PRIMARY KEY REFERENCES users(id))""")
            cur.execute("""CREATE TABLE sessions(
              id BIGSERIAL PRIMARY KEY,
              user_id BIGINT NOT NULL REFERENCES users(id),
              token_hash TEXT NOT NULL,expires_at TIMESTAMPTZ NOT NULL,
              user_agent TEXT,device_label TEXT,ip_hash TEXT,
              last_seen_at TIMESTAMPTZ,revoked_at TIMESTAMPTZ)""")
        for file in ("034_verified_email_login.sql","035_verified_password_accounts.sql"):
            with db.cursor() as cur:
                cur.execute((ROOT/"database/migrations"/file).read_text(encoding="utf-8"))
            print("PASS migration",file)

def main():
    make_database()
    client={"name":"صالح مساعد","email":"client@example.com","phone":"0512345678",
            "password":"PasswordSecure123!","role":"client"}
    code,data=register(client,connect,SECRET,deliver=send)
    assert_true(code==201 and data["email_verification_required"],"registration failed")
    assert_true(MAILED[-1][0]=="client@example.com","activation email was not sent")
    first_activation=MAILED[-1][2]
    code,payload=login({"email":client["email"],"password":client["password"]},
                       connect,SECRET,"",30,"IntegrationTest","127.0.0.1")
    assert_true(code==403 and payload["error"]=="email_not_verified",
                "unverified client can log in")
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("SELECT phone,name,email_verified_at,password_hash FROM users WHERE email=%s",
                        (client["email"],))
            row=cur.fetchone()
            assert_true(row[0]=="+966512345678" and row[1]==client["name"] and row[2] is None,
                        "registration contact fields are incorrect")
            assert_true(client["password"] not in row[3],"password stored as plaintext")

    # Resend invalidates prior link; throttle must prevent repeated spam.
    code,_=resend_verification({"email":client["email"]},connect,SECRET,deliver=send)
    assert_true(code==429,"verification resend not throttled")
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("""UPDATE account_email_actions SET created_at=now()-interval '2 minutes'
                           WHERE action='verify'""")
    code,_=resend_verification({"email":client["email"]},connect,SECRET,deliver=send)
    assert_true(code==200 and len(MAILED)==2,"resend activation failed")
    activation=MAILED[-1][2]
    assert_true(activation!=first_activation,"resend reused existing token")
    assert_true(consume_email_link({"token":first_activation},connect,SECRET,"")[0]==400,
                "old verification token remains active")
    assert_true(consume_email_link({"token":activation},connect,SECRET,"")[0]==200,
                "email activation failed")
    assert_true(consume_email_link({"token":activation},connect,SECRET,"")[0]==400,
                "used verification link accepted")
    code,data=login({"email":client["email"],"password":client["password"]},
                     connect,SECRET,"",30,"IntegrationTest","127.0.0.1")
    assert_true(code==200 and data["user"]["role"]=="client" and len(data["session_raw"])==64,
                "verified client failed login")
    assert_true(login({"email":client["email"],"password":"WrongPassword0000"},
                      connect,SECRET,"",30,"IntegrationTest","")[0]==401,
                "bad password accepted")
    assert_true(register(client,connect,SECRET,deliver=send)[0]==409,
                "duplicate signup accepted")
    assert_true(register({**client,"email":"other@example.com"},connect,SECRET,deliver=send)[0]==409,
                "duplicate phone accepted")
    print("PASS registration, saved profile, hashed password, activation and single-use resend")

    # Password recovery must revoke every existing session.
    code,response=request_password_reset({"email":client["email"]},connect,SECRET,deliver=send)
    assert_true(code==200,"password recovery request failed")
    reset=MAILED[-1][2]
    assert_true(request_password_reset({"email":"nobody@example.com"},
               connect,SECRET,deliver=send)[0]==200,
               "nonexistent accounts reveal themselves")
    assert_true(reset_password({"token":reset,"password":"myNewPassphrase123!"},
               connect,SECRET)[0]==200,"password reset failed")
    assert_true(reset_password({"token":reset,"password":"anotherPassphrase123!"},
               connect,SECRET)[0]==400,"reset token can be reused")
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("""SELECT count(*) FROM sessions s JOIN users u ON u.id=s.user_id
              WHERE u.email=%s AND s.revoked_at IS NULL""",(client["email"],))
            assert_true(cur.fetchone()[0]==0,"password reset did not revoke sessions")
    assert_true(login({"email":client["email"],"password":client["password"]},
                connect,SECRET,"",30,"CI","")[0]==401,"old password still works")
    assert_true(login({"email":client["email"],"password":"myNewPassphrase123!"},
                connect,SECRET,"",30,"CI","")[0]==200,"new password fails")
    print("PASS password recovery, single-use link, expired sessions and password rotation")

    # Email allowlisting only upgrades the verified admin address.
    admin={"name":"مدير منجاز","email":"owner@example.com","phone":"0534567890",
           "password":"OwnerPassword123!","role":"client"}
    assert_true(register(admin,connect,SECRET,deliver=send)[0]==201,
                "admin registration failed")
    token=MAILED[-1][2]
    assert_true(consume_email_link({"token":token},connect,SECRET,"owner@example.com")[0]==200,
                "admin email activation failed")
    code,data=login({"email":"owner@example.com","password":admin["password"]},
        connect,SECRET,"owner@example.com",30,"CI","")
    assert_true(code==200 and data["user"]["role"]=="admin",
                "allowlisted admin cannot sign in")
    assert_true(login({"email":"owner@example.com","password":admin["password"]},
        connect,SECRET,"another@example.com",30,"CI","")[0]==403,
                "admin role accessible when allowlist changes")
    print("PASS owner-only admin email role and allowlist enforcement")

    freelancer={"name":"مستقل منجاز","email":"freelancer@example.com",
                "phone":"0551234567","password":"FreelancePassword12!","role":"freelancer"}
    assert_true(register(freelancer,connect,SECRET,deliver=send)[0]==201,
                "freelancer registration failed")
    assert_true(consume_email_link({"token":MAILED[-1][2]},connect,SECRET,"")[0]==200,
                "freelancer verification failed")
    code,data=login({"email":freelancer["email"],"password":freelancer["password"]},
                    connect,SECRET,"",30,"CI","")
    assert_true(code==200 and data["user"]["role"]=="freelancer",
                "freelancer login failed")
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("""SELECT count(*) FROM freelancer_profiles fp
               JOIN users u ON u.id=fp.user_id WHERE u.email=%s""",(freelancer["email"],))
            assert_true(cur.fetchone()[0]==1,"freelancer profile missing")
    print("PASS client, freelancer, administrator verified email-password lifecycle")

    # Deleted account links must never be able to re-enable or modify an account.
    archived={"name":"حساب محذوف","email":"archived@example.com",
              "phone":"0561234567","password":"ArchivedPassphrase123!","role":"client"}
    assert_true(register(archived,connect,SECRET,deliver=send)[0]==201,
                "deleted account fixture registration failed")
    archived_link=MAILED[-1][2]
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("UPDATE users SET deleted_at=now() WHERE email=%s",
                        (archived["email"],))
    assert_true(consume_email_link({"token":archived_link},connect,SECRET,"")[0]==400,
                "deleted account was reactivated using a verification link")
    messages_before=len(MAILED)
    assert_true(resend_verification({"email":archived["email"]},connect,SECRET,deliver=send)[0]==200
                and len(MAILED)==messages_before,
                "deleted account received an activation email")
    assert_true(request_password_reset({"email":archived["email"]},
                connect,SECRET,deliver=send)[0]==200 and len(MAILED)==messages_before,
                "deleted account password recovery exposed or sent email")

    assert_true(request_password_reset({"email":freelancer["email"]},
                connect,SECRET,deliver=send)[0]==200,
                "freelancer password reset fixture failed")
    pending_reset=MAILED[-1][2]
    with connect() as db:
        with db.cursor() as cur:
            cur.execute("UPDATE users SET deleted_at=now() WHERE email=%s",
                        (freelancer["email"],))
    assert_true(reset_password({"token":pending_reset,"password":"AReallyNewPassword123!"},
                connect,SECRET)[0]==400,
                "deleted account password changed with a stale reset link")
    print("PASS deleted users cannot activate, resend verification, or reset passwords")

if __name__=="__main__":
    main()
