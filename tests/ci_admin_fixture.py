"""Issue administrator sessions ONLY inside disposable localhost GitHub CI test DB.

Never enable a dev OTP admin bypass or invoke this helper against hosted services.
An authenticated production user must still use the configured verification flow.
"""
import hashlib
import os
import secrets
from urllib.parse import urlsplit

def require_isolated_ci(env=None, phone=None):
    env=os.environ if env is None else env
    if env.get("CI")!="true" or env.get("E2E_CI_ADMIN_FIXTURE")!="1":
        raise RuntimeError("CI administrator fixture is disabled")
    if env.get("APP_ENV")!="beta" or env.get("EMAIL_AUTH_REQUIRED","0")=="1":
        raise RuntimeError("CI fixture cannot run with production/verified-email policy")
    if env.get("SMS_MODE")!="dev" or env.get("PAYMENT_MODE") not in ("mock","adapter"):
        raise RuntimeError("CI fixture requires test payment mode and dev-only OTP")
    if not phone or phone!=env.get("ADMIN_PHONE"):
        raise RuntimeError("CI fixture administrator phone mismatch")
    if len(env.get("AUTH_SECRET",""))<32 or env["AUTH_SECRET"]=="dev-secret-change-me":
        raise RuntimeError("CI fixture requires a non-default test secret")

    try:
        target=urlsplit(env.get("E2E_BASE_URL",""))
        db=urlsplit(env.get("DATABASE_URL",""))
        target_ok=(target.scheme=="http" and target.hostname=="127.0.0.1"
                   and target.port==3000 and target.path in ("","/")
                   and not target.username and not target.password
                   and not target.query and not target.fragment)
        db_ok=(db.scheme in ("postgres","postgresql")
               and db.hostname=="127.0.0.1" and db.port==5432
               and db.path=="/minjaz" and db.username=="minjaz"
               and bool(db.password) and not db.query and not db.fragment)
    except (ValueError,TypeError):
        raise RuntimeError("CI fixture invalid localhost URL") from None
    if not target_ok or not db_ok:
        raise RuntimeError("CI administrator fixture refuses remote or unknown databases")
    return True


def issue_local_admin_session(phone, name):
    """Seed a test-only admin session in the ephemeral PostgreSQL service."""
    require_isolated_ci(phone=phone)
    import psycopg2

    secret=os.environ["AUTH_SECRET"]
    token=secrets.token_hex(32)
    token_hash=hashlib.sha256((token+secret).encode("utf-8")).hexdigest()
    conn=psycopg2.connect(os.environ["DATABASE_URL"],connect_timeout=5)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO users(phone,name,role,is_verified)
                               VALUES(%s,%s,'admin',true)
                               ON CONFLICT (phone) DO UPDATE SET
                                 name=EXCLUDED.name,role='admin',is_verified=true
                               RETURNING id""",(phone,str(name)[:120]))
                user_id=cur.fetchone()[0]
                cur.execute("""INSERT INTO user_roles(user_id,role,enabled)
                               VALUES(%s,'admin',true)
                               ON CONFLICT(user_id,role) DO UPDATE SET enabled=true""",(user_id,))
                cur.execute("""INSERT INTO sessions(user_id,token_hash,expires_at,
                                      user_agent,device_label,last_seen_at)
                               VALUES(%s,%s,now()+interval '2 hours',
                                      'MINJAZ ephemeral CI test','CI test',now())""",
                            (user_id,token_hash))
        return {"token":token,"user":{"id":user_id,"phone":phone,
                "name":name,"role":"admin","roles":["admin"]},"roles":["admin"]}
    finally:
        conn.close()
