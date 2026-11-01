"""Explicit, email-confirmed enrollment for the preconfigured MINJAZ owner.

Configuring ADMIN_EMAIL does not itself promote accounts. The existing verified
owner signs in with their password, requests a 15-minute email challenge, then
confirms it with the account password again. Only the configured owner is allowed.
This is intentionally disabled outside the isolated preview environment.
"""
import os
import psycopg2.extras
from minjaz_email_auth import normalize_email
from minjaz_account_auth import (valid_password, verify_password, new_action,
                                 token_digest, deliver_link, secure_config)


def _eligible(row, admin_email):
    return bool(row and normalize_email(admin_email)
                and normalize_email(row.get("email")) == normalize_email(admin_email)
                and row.get("email_verified_at") is not None
                and row.get("password_hash"))


def _preview_ready(admin_email):
    return (os.environ.get("APP_ENV", "").strip().lower() == "preview"
            and bool(normalize_email(admin_email))
            and secure_config())


def request_owner_claim(user_id, password, connect, secret, admin_email,
                        deliver=deliver_link):
    if not _preview_ready(admin_email):
        return 503, {"error": "admin_setup_unavailable"}
    if not valid_password(password):
        return 403, {"error": "invalid_credentials"}
    conn = connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT email,password_hash,email_verified_at,role
                           FROM users WHERE id=%s AND deleted_at IS NULL""", (int(user_id),))
            record = cur.fetchone()
            if not record:
                return 403, {"error": "admin_claim_not_allowed"}
            # RealDictCursor is configured for account connections.
            row = dict(record)
            if not _eligible(row, admin_email):
                return 403, {"error": "admin_claim_not_allowed"}
            if not verify_password(password, row["password_hash"]):
                return 403, {"error": "invalid_credentials"}
            if row.get("role") == "admin":
                return 200, {"already_admin": True}
            cur.execute("""SELECT count(*)::int AS n,
                              extract(epoch from (now()-max(created_at))) AS elapsed
                           FROM account_email_actions
                           WHERE user_id=%s AND action='admin_claim'
                             AND created_at>now()-interval '1 hour'""", (int(user_id),))
            recent = dict(cur.fetchone())
            if recent["n"] >= 3 or (recent["elapsed"] is not None and recent["elapsed"] < 60):
                return 429, {"error": "admin_claim_rate_limited"}
            raw = new_action(cur, user_id, "admin_claim", secret)
        conn.commit()
        try:
            deliver(row["email"], "admin_claim", raw)
        except Exception:
            return 502, {"error": "email_delivery_failed"}
        return 200, {"email_confirmation_required": True, "expires_in_seconds": 900}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def confirm_owner_claim(user_id, session_id, password, raw, connect, secret, admin_email):
    if not _preview_ready(admin_email):
        return 503, {"error": "admin_setup_unavailable"}
    if not valid_password(password):
        return 403, {"error": "invalid_credentials"}
    if not isinstance(raw, str) or not 35 <= len(raw) <= 160 or not raw.isascii():
        return 400, {"error": "invalid_token"}
    digest = token_digest(secret, raw)
    conn = connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""SELECT id,email,password_hash,email_verified_at,role
                           FROM users WHERE id=%s AND deleted_at IS NULL
                           FOR UPDATE""", (int(user_id),))
            record = cur.fetchone()
            if not record:
                conn.rollback()
                return 403, {"error": "admin_claim_not_allowed"}
            row = dict(record)
            if not _eligible(row, admin_email):
                conn.rollback()
                return 403, {"error": "admin_claim_not_allowed"}
            if not verify_password(password, row["password_hash"]):
                conn.rollback()
                return 403, {"error": "invalid_credentials"}
            cur.execute("""SELECT id,(expires_at <= now()) AS expired
                           FROM account_email_actions
                           WHERE user_id=%s AND action='admin_claim' AND token_hash=%s
                             AND used_at IS NULL FOR UPDATE""", (int(user_id), digest))
            challenge = cur.fetchone()
            if not challenge:
                conn.rollback()
                return 400, {"error": "invalid_or_used_link"}
            if challenge["expired"]:
                conn.rollback()
                return 410, {"error": "email_link_expired"}
            cur.execute("""UPDATE users SET role='admin' WHERE id=%s AND email=%s
                           AND email_verified_at IS NOT NULL""",
                        (int(user_id), normalize_email(admin_email)))
            if cur.rowcount != 1:
                conn.rollback()
                return 403, {"error": "admin_claim_not_allowed"}
            cur.execute("""UPDATE user_roles SET enabled=false
                           WHERE user_id=%s AND role<>'admin'""", (int(user_id),))
            cur.execute("""INSERT INTO user_roles(user_id,role,enabled)
                           VALUES (%s,'admin',true)
                           ON CONFLICT(user_id,role) DO UPDATE SET enabled=true""", (int(user_id),))
            cur.execute("UPDATE account_email_actions SET used_at=now() WHERE id=%s",
                        (challenge["id"],))
            cur.execute("""UPDATE account_email_actions SET used_at=now()
                           WHERE user_id=%s AND action='admin_claim' AND used_at IS NULL""",
                        (int(user_id),))
            cur.execute("""UPDATE sessions SET revoked_at=now()
                           WHERE user_id=%s AND id<>%s AND revoked_at IS NULL""",
                        (int(user_id), int(session_id)))
            cur.execute("""INSERT INTO account_activity
                           (user_id,session_id,event_type,label,meta)
                           VALUES (%s,%s,'owner_admin_claim',
                                   'تم تفعيل صلاحيات الإدارة بعد التحقق بكلمة المرور والبريد',
                                   '{}'::jsonb)""", (int(user_id), int(session_id)))
        conn.commit()
        return 200, {"admin_activated": True, "other_sessions_revoked": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
