#!/usr/bin/env python3
"""Read-only, aggregate-only inventory before MINJAZ switches existing users to email auth.

Does NOT migrate users, link phone identities, change records, print contacts,
send email, or unlock production rollout. Requires explicit CLI opt-in.
"""
import argparse
import json
import os
import sys

REQUIRED_COLUMNS = {
    "users": {"id", "name", "phone", "email", "password_hash",
              "email_verified_at", "deleted_at", "role"},
    "sessions": {"user_id", "revoked_at", "expires_at"},
}
OPTIONAL_ORDER_COLUMNS = {"client_id", "freelancer_id"}

BLOCKED = """(u.deleted_at IS NULL AND (
    u.email IS NULL OR btrim(u.email)='' OR u.email_verified_at IS NULL
    OR u.password_hash IS NULL OR btrim(u.password_hash)=''
    OR u.phone IS NULL OR u.phone !~ '^\\+9665[0-9]{8}$'
    OR u.name IS NULL OR length(btrim(u.name))<2
))"""

def audit_counts(connect):
    """Use a repeatable-read READ ONLY transaction; never retrieve account identifiers."""
    db = connect()
    try:
        with db.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cur.execute("""SELECT table_name, column_name
                           FROM information_schema.columns
                           WHERE table_schema=current_schema()
                             AND table_name IN ('users','sessions','orders')""")
            cols={}
            for table,column in cur.fetchall():
                cols.setdefault(table,set()).add(column)
            absent={t:sorted(want-cols.get(t,set())) for t,want in REQUIRED_COLUMNS.items()
                    if not want.issubset(cols.get(t,set()))}
            if absent:
                raise RuntimeError("account_email_schema_not_ready: "+json.dumps(absent,sort_keys=True))
            cur.execute("""SELECT
                  count(*) FILTER (WHERE deleted_at IS NULL) AS active_accounts,
                  count(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted_accounts,
                  count(*) FILTER (WHERE deleted_at IS NOT NULL AND email IS NOT NULL
                    AND btrim(email)<>'') AS deleted_accounts_retaining_email,
                  count(*) FILTER (WHERE deleted_at IS NOT NULL
                    AND password_hash IS NOT NULL) AS deleted_accounts_retaining_password_hash,
                  count(*) FILTER (WHERE deleted_at IS NOT NULL
                    AND email_verified_at IS NOT NULL) AS deleted_accounts_retaining_verified_marker,
                  count(*) FILTER (WHERE deleted_at IS NULL
                    AND (email IS NULL OR btrim(email)='')) AS active_phone_only,
                  count(*) FILTER (WHERE deleted_at IS NULL
                    AND email IS NOT NULL AND btrim(email)<>''
                    AND email_verified_at IS NULL) AS active_email_unverified,
                  count(*) FILTER (WHERE deleted_at IS NULL
                    AND (password_hash IS NULL OR btrim(password_hash)='')) AS active_no_password,
                  count(*) FILTER (WHERE deleted_at IS NULL
                    AND (phone IS NULL OR phone !~ '^\\+9665[0-9]{8}$'
                    OR name IS NULL OR length(btrim(name))<2)) AS active_incomplete_profile,
                  count(*) FILTER (WHERE deleted_at IS NULL AND role='admin') AS active_admins,
                  count(*) FILTER (WHERE """+BLOCKED.replace("u.","")+""") AS blocked_by_email_only
                FROM users""")
            keys=("active_accounts","deleted_accounts","deleted_accounts_retaining_email",
                  "deleted_accounts_retaining_password_hash",
                  "deleted_accounts_retaining_verified_marker","active_phone_only",
                  "active_email_unverified","active_no_password",
                  "active_incomplete_profile","active_admins","blocked_by_email_only")
            totals={name:int(value) for name,value in zip(keys,cur.fetchone())}
            cur.execute("""SELECT count(DISTINCT s.user_id)
                           FROM sessions s JOIN users u ON u.id=s.user_id
                           WHERE s.revoked_at IS NULL AND s.expires_at>now()
                             AND """+BLOCKED)
            totals["blocked_with_active_sessions"]=int(cur.fetchone()[0])
            if OPTIONAL_ORDER_COLUMNS.issubset(cols.get("orders",set())):
                cur.execute("""SELECT count(*)
                               FROM users u
                               WHERE """+BLOCKED+"""
                                 AND EXISTS (
                                   SELECT 1 FROM orders o
                                   WHERE o.client_id=u.id OR o.freelancer_id=u.id
                                 )""")
                totals["blocked_with_orders"]=int(cur.fetchone()[0])
            else:
                totals["blocked_with_orders"]=None
        db.rollback()  # Leave no transaction open; read-only throughout.
        return {
            "report":"minjaz_legacy_email_transition_inventory_v1",
            "contains_personal_data":False,
            "writes_performed":False,
            "counts":totals,
            "account_migration_required":bool(totals["blocked_by_email_only"]),
            "privacy_deletion_review_required":bool(
                totals["deleted_accounts_retaining_email"]
                or totals["deleted_accounts_retaining_password_hash"]
                or totals["deleted_accounts_retaining_verified_marker"]
            ),
            "privacy_deletion_gate":(
                "review_required" if (
                    totals["deleted_accounts_retaining_email"]
                    or totals["deleted_accounts_retaining_password_hash"]
                    or totals["deleted_accounts_retaining_verified_marker"]
                ) else "no_retained_email_credentials_detected"
            ),
            "email_policy_switch_account_gate":(
                "blocked" if totals["blocked_by_email_only"] else "no_incompatible_active_accounts_detected"
            ),
            "caveat":"Read-only aggregate audit; detected legacy deletion residue must be handled "
                     "through approved data-retention remediation, not automatic deletion. "
                     "Email delivery, admin allowlist, KYC, storage, legal and payout "
                     "readiness require separate verified checks.",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only aggregate legacy-account audit")
    parser.add_argument("--confirm-read-only",action="store_true",
                        help="Required: perform SELECT-only inventory without contact details")
    args=parser.parse_args(argv)
    if not args.confirm_read_only:
        parser.error("pass --confirm-read-only to acknowledge a read-only audit")
    if not os.getenv("DATABASE_URL"):
        print("FAIL: DATABASE_URL missing; no connection attempted",file=sys.stderr)
        return 2
    try:
        import psycopg2
        def connect():
            return psycopg2.connect(os.environ["DATABASE_URL"],
                     options="-c default_transaction_read_only=on",connect_timeout=8)
        output=audit_counts(connect)
    except Exception as err:
        # Never print DSNs, SQL parameters, phone numbers or error messages from the driver.
        print("FAIL: "+("schema_incomplete" if str(err).startswith("account_email_schema_not_ready:")
                        else type(err).__name__),file=sys.stderr)
        return 1
    print(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
