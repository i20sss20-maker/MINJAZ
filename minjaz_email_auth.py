"""Passwordless email login for MINJAZ preview. No SMS or public demo OTP.

Verified mailbox ownership is the only way to create an email session. Existing
phone-registered users are not merged automatically; linking needs an existing
authenticated session and a separate verified flow.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
import urllib.error
import urllib.request
import uuid
from email.message import EmailMessage

import psycopg2
import psycopg2.extras

EMAIL_PATTERN = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+\Z"
)


def normalize_email(raw):
    if not isinstance(raw, str) or len(raw) > 254 or any(ord(ch) < 33 for ch in raw.strip()):
        return ""
    email = raw.strip().lower()
    if len(email) > 254 or len(email.split("@")[0]) > 64 or ".." in email:
        return ""
    return email if EMAIL_PATTERN.fullmatch(email) else ""


def email_delivery_config(env=None):
    env = env or os.environ
    mode = env.get("EMAIL_MODE", "off").strip().lower()
    from_addr = normalize_email(env.get("EMAIL_FROM", ""))
    secret = env.get("AUTH_SECRET", "")
    secure_secret = len(secret) >= 32 and secret != "dev-secret-change-me"
    if mode == "resend":
        ready = bool(from_addr and env.get("RESEND_API_KEY", "").startswith("re_") and secure_secret)
    elif mode == "smtp":
        try:
            port = int(env.get("SMTP_PORT", "587"))
        except ValueError:
            port = 0
        ready = bool(from_addr and port in (465, 587) and env.get("SMTP_HOST")
                     and env.get("SMTP_USERNAME") and env.get("SMTP_PASSWORD") and secure_secret)
    else:
        ready = False
    return {"enabled": ready, "mode": mode if mode in ("smtp", "resend") else "off"}


def send_email_code(email, code, env=None):
    env = env or os.environ
    state = email_delivery_config(env)
    if not state["enabled"]:
        raise RuntimeError("email_delivery_not_configured")
    msg = EmailMessage()
    msg["From"] = env["EMAIL_FROM"]
    msg["To"] = email
    msg["Subject"] = "MINJAZ | رمز تسجيل الدخول"
    msg.set_content(
        "رمز الدخول إلى منجاز: " + code +
        "\nتنتهي صلاحية الرمز خلال 10 دقائق. إذا لم تطلبه، فتجاهل الرسالة.\n",
        subtype="plain", charset="utf-8",
    )
    if state["mode"] == "smtp":
        host = env["SMTP_HOST"]
        port = int(env.get("SMTP_PORT", "587"))
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12, context=context) as server:
                server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
                server.send_message(msg)
    else:
        data = json.dumps({
            "from": "MINJAZ <" + env["EMAIL_FROM"] + ">",
            "to": [email],
            "subject": "MINJAZ | رمز تسجيل الدخول",
            "text": msg.get_content(),
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails", data=data, method="POST",
            headers={"Authorization": "Bearer " + env["RESEND_API_KEY"],
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status not in (200, 201):
                raise RuntimeError("email_provider_failure")
            response.read(8192)


def code_digest(secret, challenge_id, code):
    return hmac.new(secret.encode("utf-8"), (challenge_id + ":" + code).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def request_email_otp(body, connect, secret, deliver, ip_allowed=True, config_ready=True):
    if not config_ready or len(secret) < 32 or secret == "dev-secret-change-me":
        return 503, {"error": "email_not_configured"}
    if not isinstance(body, dict):
        return 400, {"error": "invalid_payload"}
    email = normalize_email(body.get("email"))
    role = body.get("role")
    if not email:
        return 400, {"error": "invalid_email"}
    if role not in ("client", "freelancer"):
        return 400, {"error": "invalid_role"}
    if not ip_allowed:
        return 429, {"error": "otp_source_rate_limited", "retry_after_seconds": 600}

    challenge_id = str(uuid.uuid4())
    code = f"{secrets.randbelow(1000000):06d}"
    conn = connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT count(*)::int AS n,
                    extract(epoch from (now()-max(created_at)))::float8 AS seconds
                FROM email_login_challenges
                WHERE email=%s AND created_at>now()-interval '10 minutes'""", (email,))
            row = cur.fetchone()
            if row["n"] >= 5:
                return 429, {"error": "otp_rate_limited", "retry_after_seconds": 600}
            if row["seconds"] is not None and row["seconds"] < 60:
                return 429, {"error": "otp_wait", "retry_after_seconds": max(1, int(60-row["seconds"]))}
            cur.execute("""INSERT INTO email_login_challenges
                (challenge_id,email,requested_role,code_hash,expires_at)
                VALUES (%s,%s,%s,%s,now()+interval '10 minutes')""",
                (challenge_id, email, role, code_digest(secret, challenge_id, code)))
        conn.commit()
        try:
            deliver(email, code)
        except Exception:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM email_login_challenges WHERE challenge_id=%s AND verified_at IS NULL",
                            (challenge_id,))
            conn.commit()
            return 502, {"error": "email_delivery_failed"}
        return 201, {"challenge_id": challenge_id, "code_length": 6,
                     "expires_in_seconds": 600, "delivery": "email"}
    finally:
        conn.close()


def verify_email_otp(body, connect, secret, admin_email, transport_ready,
                     session_ttl_days, user_agent, ip_address):
    if not transport_ready or len(secret) < 32 or secret == "dev-secret-change-me":
        return 503, {"error": "email_not_configured"}
    if not isinstance(body, dict):
        return 400, {"error": "invalid_payload"}
    challenge_id = body.get("challenge_id")
    code = body.get("code")
    name = str(body.get("name") or "مستخدم").strip()[:120]
    if not isinstance(challenge_id, str) or not isinstance(code, str):
        return 400, {"error": "invalid_code"}
    try:
        challenge_id = str(uuid.UUID(challenge_id))
    except (ValueError, AttributeError):
        return 400, {"error": "invalid_code"}
    if not re.fullmatch(r"[0-9]{6}", code):
        return 400, {"error": "invalid_code"}
    if len(name) < 2:
        return 400, {"error": "invalid_name"}

    conn = connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT id,email,requested_role,code_hash,attempts,verified_at,
                       expires_at<=now() AS expired
                       FROM email_login_challenges WHERE challenge_id=%s FOR UPDATE""",
                        (challenge_id,))
            ch = cur.fetchone()
            if ch is None:
                return 404, {"error": "challenge_not_found"}
            if ch["verified_at"] is not None:
                return 409, {"error": "already_verified"}
            if ch["expired"]:
                return 410, {"error": "otp_expired"}
            if ch["attempts"] >= 5:
                return 429, {"error": "too_many_attempts"}
            expected = code_digest(secret, challenge_id, code)
            if not hmac.compare_digest(expected, ch["code_hash"]):
                cur.execute("UPDATE email_login_challenges SET attempts=attempts+1 WHERE id=%s",
                            (ch["id"],))
                conn.commit()
                return 401, {"error": "invalid_code"}

            is_admin = bool(admin_email and ch["email"] == normalize_email(admin_email))
            role = "admin" if is_admin else ch["requested_role"]
            cur.execute("SELECT id,role FROM users WHERE email=%s FOR UPDATE", (ch["email"],))
            existing = cur.fetchone()
            if existing and existing["role"] == "admin" and not is_admin:
                return 403, {"error": "admin_email_mismatch"}

            if existing:
                user_id = existing["id"]
                cur.execute("UPDATE users SET name=%s,role=%s,is_verified=true WHERE id=%s",
                            (name, role, user_id))
            else:
                cur.execute("""INSERT INTO users(email,name,role,is_verified)
                               VALUES (%s,%s,%s,true) RETURNING id""",
                            (ch["email"], name, role))
                user_id = cur.fetchone()["id"]

            cur.execute("""INSERT INTO user_roles(user_id,role,enabled)
                           VALUES (%s,%s,true)
                           ON CONFLICT(user_id,role) DO UPDATE SET enabled=true""",
                        (user_id, role))
            if role == "freelancer":
                cur.execute("""INSERT INTO freelancer_profiles(user_id)
                               VALUES (%s) ON CONFLICT(user_id) DO NOTHING""", (user_id,))
            cur.execute("UPDATE email_login_challenges SET verified_at=now() WHERE id=%s", (ch["id"],))
            raw = secrets.token_hex(32)
            device_label = "متصفح"
            ip_hash = hashlib.sha256((ip_address + secret).encode()).hexdigest()[:24] if ip_address else None
            cur.execute("""INSERT INTO sessions
                         (user_id,token_hash,expires_at,user_agent,device_label,ip_hash,last_seen_at)
                         VALUES (%s,%s,now()+(%s || ' days')::interval,%s,%s,%s,now())
                         RETURNING id""",
                        (user_id, hashlib.sha256((raw + secret).encode()).hexdigest(),
                         session_ttl_days, user_agent[:500], device_label, ip_hash))
            session_id = cur.fetchone()["id"]
            cur.execute("SELECT role FROM user_roles WHERE user_id=%s AND enabled=true",
                        (user_id,))
            roles = [row["role"] for row in cur.fetchall()]
        conn.commit()
        return 200, {"session_raw": raw, "session_id": session_id,
                     "user": {"id":user_id,"phone":None,"email":ch["email"],
                              "name":name,"role":role,"roles":roles},"roles":roles}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return 409, {"error": "email_conflict_retry"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
