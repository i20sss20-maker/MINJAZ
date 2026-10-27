#!/usr/bin/env python3
"""MINJAZ: one-recipient Resend test sender; no signup or payment side effects.

Use only in the dedicated isolated Railway sandbox. Does not create a mailbox,
verify a custom domain or reveal API keys. Provider acceptance is not inbox proof.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# Executing "python scripts/probe_minjaz_resend_sender.py" sets sys.path[0]
# to /app/scripts, not /app. Make the sibling first-party email module visible
# without depending on PYTHONPATH, inside both Railway and local operator shells.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SANDBOX_PROJECT_ID = "b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4"
SANDBOX_ENVIRONMENT_ID = "d3e2f4a8-582d-4c3d-b6c8-cc919b2dac78"
SANDBOX_SERVICE_ID = "7d61ddbd-d1c3-40d2-ac57-09c4f0c2cdcf"
TEST_SENDER = "onboarding@resend.dev"
TEST_ENDPOINT = "https://api.resend.com/emails"


def readiness(env):
    """Return only public configuration status, never secret or recipient values."""
    from minjaz_email_auth import normalize_email
    missing = []
    if env.get("RAILWAY_PROJECT_ID") != SANDBOX_PROJECT_ID:
        missing.append("dedicated_sandbox_project")
    if env.get("RAILWAY_ENVIRONMENT_ID") != SANDBOX_ENVIRONMENT_ID:
        missing.append("dedicated_sandbox_environment")
    if env.get("RAILWAY_SERVICE_ID") != SANDBOX_SERVICE_ID:
        missing.append("dedicated_sandbox_service")
    if env.get("APP_ENV", "").lower() != "preview":
        missing.append("preview_environment")
    if env.get("EMAIL_MODE", "").lower() != "resend":
        missing.append("EMAIL_MODE=resend")
    if env.get("EMAIL_FROM", "").lower() != TEST_SENDER:
        missing.append("EMAIL_FROM=onboarding@resend.dev")
    if not env.get("RESEND_API_KEY", "").startswith("re_"):
        missing.append("RESEND_API_KEY")
    if len(env.get("AUTH_SECRET", "")) < 32 or env.get("AUTH_SECRET") == "dev-secret-change-me":
        missing.append("AUTH_SECRET")
    if not normalize_email(env.get("RESEND_TEST_RECIPIENT", "")):
        missing.append("RESEND_TEST_RECIPIENT")
    return {"test_sender":TEST_SENDER, "ready":not missing, "missing":missing,
            "scope":"sandbox_only", "has_created_mailbox":False}


def send_test(env, transport=None):
    state=readiness(env)
    if not state["ready"]:
        raise RuntimeError("sandbox_mail_not_ready")
    recipient=env["RESEND_TEST_RECIPIENT"].strip().lower()
    data=json.dumps({
        "from":"MINJAZ Test <"+TEST_SENDER+">",
        "to":[recipient],
        "subject":"MINJAZ | اختبار البريد التجريبي",
        "text":("هذه رسالة اختبار لإرسال بريد منجاز عبر Resend.\n"
                "لا تحتوي على رابط تفعيل حساب حقيقي.\n"
                "إذا وصلت إلى بريدك، يمكن متابعة اختبار التسجيل وتفعيل الحساب على بيئة التجربة.\n"),
    }, ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(
        TEST_ENDPOINT, data=data, method="POST",
        headers={"Authorization":"Bearer "+env["RESEND_API_KEY"],
                 "Content-Type":"application/json"},
    )
    connect=transport or urllib.request.urlopen
    try:
        with connect(req,timeout=15) as response:
            if response.status not in (200,201):
                return {"result":"provider_rejected", "status":response.status}
            response.read(8192)
            return {"result":"accepted_by_provider", "status":response.status,
                    "inbox_delivery_confirmed":False}
    except urllib.error.HTTPError as exc:
        # Never print response body: some providers echo sender, recipient or IDs.
        return {"result":"provider_rejected", "status":exc.code}
    except (OSError,TimeoutError):
        return {"result":"network_failure", "status":None}


def main(argv=None):
    p=argparse.ArgumentParser(description="Inspect or send a MINJAZ sandbox-only Resend test email")
    p.add_argument("--send",action="store_true",
                   help="Explicitly send one test to the sandbox configured recipient")
    p.add_argument("--confirm-sandbox-send",action="store_true",
                   help="Required together with --send: do not run against real customers")
    args=p.parse_args(argv)
    current=readiness(os.environ)
    if not args.send:
        print(json.dumps(current,sort_keys=True))
        return 0 if current["ready"] else 2
    if not args.confirm_sandbox_send:
        p.error("--send requires --confirm-sandbox-send")
    if not current["ready"]:
        print(json.dumps(current,sort_keys=True))
        return 2
    outcome=send_test(os.environ)
    print(json.dumps(outcome,sort_keys=True))
    return 0 if outcome["result"]=="accepted_by_provider" else 1

if __name__=="__main__":
    sys.exit(main())
