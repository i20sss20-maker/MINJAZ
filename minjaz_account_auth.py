"""MINJAZ email-confirmed accounts: registration, login, resend and password recovery.

A verified mailbox and completed profile are mandatory for access. Passwords
are salted using hashlib.scrypt. Verification/recovery links contain random
single-use tokens; only HMAC digests are stored. No demo credential or token
is returned to a public caller.
"""
import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
import urllib.request
import json
from email.message import EmailMessage

import psycopg2
import psycopg2.extras
from minjaz_email_auth import normalize_email, email_delivery_config

def clean_phone(raw):
    if not isinstance(raw,str): return ""
    chars = "".join(ch for ch in raw if ch.isascii() and ch.isdigit())
    if chars.startswith("00966"): chars=chars[2:]
    if chars.startswith("966") and len(chars)==12 and chars[3]=="5":return "+"+chars
    if chars.startswith("05") and len(chars)==10:return "+966"+chars[1:]
    if chars.startswith("5") and len(chars)==9:return "+966"+chars
    return ""

def valid_password(value):
    return isinstance(value,str) and 10<=len(value)<=128 and len(value.encode("utf-8"))<=512

def hash_password(password,salt=None):
    if not valid_password(password):raise ValueError("invalid_password")
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode("utf-8"),salt=salt,n=16384,r=8,p=1,dklen=32)
    return "scrypt$16384$8$1$"+salt.hex()+"$"+digest.hex()

def verify_password(password,stored):
    if not valid_password(password) or not isinstance(stored,str):return False
    try:
        algorithm,n,r,p,salt,digest=stored.split("$")
        if algorithm!="scrypt" or (n,r,p)!=("16384","8","1"):return False
        salt_b=bytes.fromhex(salt);expected=bytes.fromhex(digest)
        if len(salt_b)!=16 or len(expected)!=32:return False
        actual=hashlib.scrypt(password.encode("utf-8"),salt=salt_b,n=16384,r=8,p=1,dklen=32)
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError):return False

def token_digest(secret,raw):
    return hmac.new(secret.encode("utf-8"),raw.encode("ascii"),hashlib.sha256).hexdigest()

def secure_config(config=None):
    env=config or os.environ
    secret=env.get("AUTH_SECRET","")
    base=env.get("PUBLIC_BASE_URL","").strip().rstrip("/")
    return len(secret)>=32 and secret!="dev-secret-change-me" and base.startswith("https://") and email_delivery_config(env)["enabled"]

def deliver_link(address,action,raw,config=None):
    env=config or os.environ
    if not secure_config(env):raise RuntimeError("email_not_configured")
    base=env["PUBLIC_BASE_URL"].strip().rstrip("/")
    key="verify-email" if action=="verify" else "reset-password"
    url=base+"/#"+key+"="+raw
    title="تفعيل حساب منجاز" if action=="verify" else "إعادة تعيين كلمة مرور منجاز"
    body=("مرحبًا،\n\nافتح الرابط التالي لتفعيل حسابك في منجاز:\n" if action=="verify"
          else "مرحبًا،\n\nافتح الرابط التالي لإعادة تعيين كلمة مرور حسابك في منجاز:\n")
    body+=url+("\n\nينتهي الرابط خلال 24 ساعة.\n" if action=="verify"
               else "\n\nينتهي الرابط خلال 30 دقيقة.\n")
    body+="إذا لم تطلب هذه العملية فتجاهل الرسالة.\n"
    from_email=env["EMAIL_FROM"].strip()
    mode=env["EMAIL_MODE"].strip().lower()
    if mode=="resend":
        req=urllib.request.Request(
          "https://api.resend.com/emails",method="POST",
          data=json.dumps({"from":"MINJAZ <"+from_email+">","to":[address],
                           "subject":"MINJAZ | "+title,"text":body},ensure_ascii=False).encode(),
          headers={"Authorization":"Bearer "+env["RESEND_API_KEY"],
                   "Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=12) as res:
            if res.status not in (200,201):raise RuntimeError("email_provider_failure")
            res.read(8192)
    elif mode=="smtp":
        msg=EmailMessage()
        msg["From"]=from_email;msg["To"]=address;msg["Subject"]="MINJAZ | "+title
        msg.set_content(body,charset="utf-8")
        host=env["SMTP_HOST"];port=int(env.get("SMTP_PORT","587"))
        context=ssl.create_default_context()
        if port==465:
            with smtplib.SMTP_SSL(host,port,context=context,timeout=12) as client:
                client.login(env["SMTP_USERNAME"],env["SMTP_PASSWORD"])
                client.send_message(msg)
        else:
            with smtplib.SMTP(host,port,timeout=12) as client:
                client.ehlo();client.starttls(context=context);client.ehlo()
                client.login(env["SMTP_USERNAME"],env["SMTP_PASSWORD"])
                client.send_message(msg)
    else:raise RuntimeError("email_not_configured")

def new_action(cur,user_id,action,secret):
    raw=secrets.token_urlsafe(32)
    digest=token_digest(secret,raw)
    ttl="24 hours" if action=="verify" else "30 minutes"
    cur.execute("""UPDATE account_email_actions SET used_at=now()
                   WHERE user_id=%s AND action=%s AND used_at IS NULL""",(user_id,action))
    cur.execute("""INSERT INTO account_email_actions(user_id,action,token_hash,expires_at)
                   VALUES (%s,%s,%s,now()+(%s)::interval)""",
                (user_id,action,digest,ttl))
    return raw

def register(data,connect,secret,deliver=deliver_link,ready=True):
    if not ready:return 503,{"error":"email_not_configured"}
    if not isinstance(data,dict):return 400,{"error":"invalid_payload"}
    email=normalize_email(data.get("email"))
    phone=clean_phone(data.get("phone"))
    name=data.get("name")
    password=data.get("password")
    role=data.get("role")
    if not email:return 400,{"error":"invalid_email"}
    if not phone:return 400,{"error":"invalid_phone"}
    if not isinstance(name,str) or not 2<=len(name.strip())<=120:return 400,{"error":"invalid_name"}
    if not valid_password(password):return 400,{"error":"invalid_password"}
    if role not in ("client","freelancer"):return 400,{"error":"invalid_role"}
    # Hash before opening a DB transaction.
    password_hash=hash_password(password)
    conn=connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM users WHERE email=%s OR phone=%s LIMIT 1",(email,phone))
            if cur.fetchone():return 409,{"error":"account_already_exists"}
            cur.execute("""INSERT INTO users(phone,email,name,role,password_hash,is_verified)
                           VALUES (%s,%s,%s,%s,%s,false) RETURNING id""",
                        (phone,email,name.strip(),role,password_hash))
            user_id=cur.fetchone()["id"]
            cur.execute("""INSERT INTO user_roles(user_id,role,enabled)
                           VALUES (%s,%s,true)
                           ON CONFLICT(user_id,role) DO UPDATE SET enabled=true""",(user_id,role))
            if role=="freelancer":
                cur.execute("""INSERT INTO freelancer_profiles(user_id)
                               VALUES (%s) ON CONFLICT(user_id) DO NOTHING""",(user_id,))
            raw=new_action(cur,user_id,"verify",secret)
        conn.commit()
        try:deliver(email,"verify",raw)
        except Exception:
            return 502,{"error":"email_delivery_failed","can_resend":True}
        return 201,{"registered":True,"email_verification_required":True,"delivery":"email_link"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return 409,{"error":"account_already_exists"}
    except Exception:
        conn.rollback();raise
    finally:conn.close()

def consume_email_link(data,connect,secret,admin_email):
    if not isinstance(data,dict):return 400,{"error":"invalid_payload"}
    raw=data.get("token")
    if not isinstance(raw,str) or not 35<=len(raw)<=160 or not raw.isascii():
        return 400,{"error":"invalid_token"}
    digest=token_digest(secret,raw)
    conn=connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT a.id,a.user_id,a.action,u.email,u.role,
                          a.expires_at<=now() AS expired
                          FROM account_email_actions a JOIN users u ON u.id=a.user_id
                          WHERE a.token_hash=%s AND a.action='verify'
                            AND a.used_at IS NULL FOR UPDATE OF a""",(digest,))
            row=cur.fetchone()
            if not row:return 400,{"error":"invalid_or_used_link"}
            if row["expired"]:return 410,{"error":"email_link_expired"}
            new_role="admin" if (admin_email and row["email"]==normalize_email(admin_email)) else row["role"]
            if new_role=="admin":
                cur.execute("""UPDATE users SET email_verified_at=now(),is_verified=true,role='admin'
                               WHERE id=%s""",(row["user_id"],))
                cur.execute("""INSERT INTO user_roles(user_id,role,enabled)
                               VALUES (%s,'admin',true)
                               ON CONFLICT(user_id,role) DO UPDATE SET enabled=true""",(row["user_id"],))
            else:
                cur.execute("""UPDATE users SET email_verified_at=now(),is_verified=true
                               WHERE id=%s""",(row["user_id"],))
            cur.execute("UPDATE account_email_actions SET used_at=now() WHERE id=%s",(row["id"],))
        conn.commit()
        return 200,{"verified":True}
    except Exception:
        conn.rollback();raise
    finally:conn.close()

def resend_verification(data,connect,secret,deliver=deliver_link,ready=True):
    if not ready:return 503,{"error":"email_not_configured"}
    if not isinstance(data,dict):return 400,{"error":"invalid_payload"}
    email=normalize_email(data.get("email"))
    if not email:return 400,{"error":"invalid_email"}
    conn=connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT id,email_verified_at FROM users WHERE email=%s""",(email,))
            user=cur.fetchone()
            if not user or user["email_verified_at"] is not None:
                return 200,{"message":"if_account_needs_verification_email_sent"}
            cur.execute("""SELECT extract(epoch from (now()-max(created_at))) AS elapsed,
                            count(*)::int AS n FROM account_email_actions
                            WHERE user_id=%s AND action='verify'
                              AND created_at>now()-interval '1 hour'""",(user["id"],))
            recent=cur.fetchone()
            if recent["n"]>=5:return 429,{"error":"otp_rate_limited","retry_after_seconds":3600}
            if recent["elapsed"] is not None and recent["elapsed"]<60:
                return 429,{"error":"otp_wait","retry_after_seconds":60}
            raw=new_action(cur,user["id"],"verify",secret)
        conn.commit()
        try:deliver(email,"verify",raw)
        except Exception:return 502,{"error":"email_delivery_failed"}
        return 200,{"message":"if_account_needs_verification_email_sent"}
    except Exception:
        conn.rollback();raise
    finally:conn.close()

def login(data,connect,secret,admin_email,ttl_days,agent,ip):
    if not isinstance(data,dict):return 400,{"error":"invalid_payload"}
    email=normalize_email(data.get("email"))
    password=data.get("password")
    if not email or not valid_password(password):return 401,{"error":"invalid_credentials"}
    conn=connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT id,email,phone,name,role,password_hash,email_verified_at
                           FROM users WHERE email=%s AND deleted_at IS NULL""",(email,))
            user=cur.fetchone()
            if not user or not verify_password(password,user["password_hash"]):
                return 401,{"error":"invalid_credentials"}
            if user["email_verified_at"] is None or not user["phone"] or len(user["name"].strip())<2:
                return 403,{"error":"email_not_verified"}
            if user["role"]=="admin" and (not admin_email or email!=normalize_email(admin_email)):
                return 403,{"error":"admin_email_mismatch"}
            raw=secrets.token_hex(32)
            hashed=hashlib.sha256((raw+secret).encode()).hexdigest()
            ip_hash=hashlib.sha256((ip+secret).encode()).hexdigest()[:24] if ip else None
            cur.execute("""INSERT INTO sessions(user_id,token_hash,expires_at,
                              user_agent,device_label,ip_hash,last_seen_at)
                           VALUES(%s,%s,now()+(%s || ' days')::interval,%s,%s,%s,now())
                           RETURNING id""",
                        (user["id"],hashed,ttl_days,agent[:500],"متصفح",ip_hash))
            sid=cur.fetchone()["id"]
            cur.execute("SELECT role FROM user_roles WHERE user_id=%s AND enabled=true",(user["id"],))
            roles=[r["role"] for r in cur.fetchall()]
        conn.commit()
        public={k:user[k] for k in ("id","email","phone","name","role")}
        public["roles"]=roles
        return 200,{"session_raw":raw,"session_id":sid,"user":public,"roles":roles}
    except Exception:
        conn.rollback();raise
    finally:conn.close()

def request_password_reset(data,connect,secret,deliver=deliver_link,ready=True):
    if not ready:return 503,{"error":"email_not_configured"}
    if not isinstance(data,dict):return 400,{"error":"invalid_payload"}
    email=normalize_email(data.get("email"))
    if not email:return 400,{"error":"invalid_email"}
    ok={"message":"if_account_exists_email_sent"}
    conn=connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT id FROM users WHERE email=%s AND email_verified_at IS NOT NULL
                           AND deleted_at IS NULL""",(email,))
            user=cur.fetchone()
            if not user:return 200,ok
            cur.execute("""SELECT count(*)::int AS n,extract(epoch from (now()-max(created_at))) AS elapsed
                           FROM account_email_actions WHERE user_id=%s AND action='reset'
                             AND created_at>now()-interval '1 hour'""",(user["id"],))
            last=cur.fetchone()
            if last["n"]>=5 or (last["elapsed"] is not None and last["elapsed"]<60):
                return 200,ok
            raw=new_action(cur,user["id"],"reset",secret)
        conn.commit()
        try:deliver(email,"reset",raw)
        except Exception:pass  # Avoid leaking whether this mailbox belongs to a user.
        return 200,ok
    except Exception:
        conn.rollback();raise
    finally:conn.close()

def reset_password(data,connect,secret):
    if not isinstance(data,dict):return 400,{"error":"invalid_payload"}
    raw=data.get("token");password=data.get("password")
    if not isinstance(raw,str) or not 35<=len(raw)<=160 or not raw.isascii():
        return 400,{"error":"invalid_token"}
    if not valid_password(password):return 400,{"error":"invalid_password"}
    new_hash=hash_password(password)
    conn=connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT a.id,a.user_id,a.expires_at<=now() AS expired
                           FROM account_email_actions a JOIN users u ON u.id=a.user_id
                           WHERE a.token_hash=%s AND a.action='reset' AND a.used_at IS NULL
                             AND u.email_verified_at IS NOT NULL FOR UPDATE OF a""",
                        (token_digest(secret,raw),))
            row=cur.fetchone()
            if not row:return 400,{"error":"invalid_or_used_link"}
            if row["expired"]:return 410,{"error":"email_link_expired"}
            cur.execute("UPDATE users SET password_hash=%s WHERE id=%s",(new_hash,row["user_id"]))
            cur.execute("UPDATE sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
                        (row["user_id"],))
            cur.execute("UPDATE account_email_actions SET used_at=now() WHERE id=%s",(row["id"],))
        conn.commit()
        return 200,{"password_reset":True}
    except Exception:
        conn.rollback();raise
    finally:conn.close()
