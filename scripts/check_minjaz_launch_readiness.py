#!/usr/bin/env python3
"""Public read-only checks for MINJAZ live readiness, no accounts or payments created.

Default: inspect sandbox and report beta readiness; --commercial fails closed
unless every required commercial check passes. Never prints environment secrets.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_BASE = "https://minjaz-digital-services-api-sandbox.up.railway.app"

def fetch(base,path,expect=200):
    req=urllib.request.Request(base+path,headers={"Accept":"application/json","User-Agent":"MINJAZ-read-only-launch-gate/1"})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            status=response.status
            data=json.loads(response.read(1_000_000).decode("utf-8"))
    except urllib.error.HTTPError as e:
        status=e.code
        data=json.loads(e.read(100_000).decode("utf-8"))
    if status!=expect:
        raise RuntimeError(f"{path}: HTTP {status} (expected {expect})")
    return data

# HTML and account JavaScript checks are GET-only. They catch broken links and
# missing frontend deploy assets even when JSON API health looks green.
PUBLIC_UI_CONTRACT={
    "/": ("id=\"auth\"", "id=\"app\"", "/minjaz-account-registration-v1.js"),
    "/digital-services": ("id=\"catalog\"", "id=\"orderForm\"",
                          "href=\"/signup?auth=login&amp;next=digital-services\""),
    "/signup": ("id=\"signup\"", "id=\"login\"", "id=\"recover\""),
    "/workspace": ("id=\"workspace\"", "id=\"clientAction\"", "id=\"freelancerAction\""),
    "/workspace-v1.js": ("/api/v1/me", "/api/v1/tasks", "/api/v1/legal/accept"),
    "/minjaz-account-registration-v1.js": ("minjaz-service-entry-app",
                                           "/api/v1/auth/login-email",
                                           "returnToStoreAfterLogin"),
}

def check_public_ui(root):
    for path,markers in PUBLIC_UI_CONTRACT.items():
        req=urllib.request.Request(root+path,headers={
            "Accept":"text/html,application/javascript",
            "User-Agent":"MINJAZ-read-only-launch-gate/1"})
        try:
            with urllib.request.urlopen(req,timeout=15) as response:
                status=response.status
                content_type=response.headers.get("Content-Type","").lower()
                body=response.read(1_000_000).decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{path}: HTTP {exc.code} (expected 200)") from None
        expected_type="javascript" if path.endswith(".js") else "html"
        if status!=200 or expected_type not in content_type:
            raise RuntimeError(f"{path}: missing or incorrect public page/asset response")
        # During sandbox redesign, either the old authenticated shell or
        # the premium marketing landing may serve '/'. Both must link to
        # the existing real verified-email account workflow.
        premium_home=(path=="/" and
                      all(m in body for m in ('id="hero-title"',
                                               'href="/signup"', 'class="flow-card"')))
        if not premium_home and any(marker not in body for marker in markers):
            raise RuntimeError(f"{path}: public interface contract missing")
    return True

def run(base,commercial=False):
    url=urlparse(base)
    try:
        valid_port=(url.port is None or 1<=url.port<=65535)
    except ValueError:
        valid_port=False
    if (url.scheme!="https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ("","/") or not valid_port):
        raise RuntimeError("HTTPS origin without path, credentials or query required")
    root=base.rstrip("/")
    health=fetch(root,"/health")
    if health.get("ok") is not True or health.get("database") is not True:
        raise RuntimeError("Health/database is not healthy")
    readiness=fetch(root,"/readiness")
    checks=readiness.get("checks")
    if not isinstance(checks,list) or not all(isinstance(c,dict) and isinstance(c.get("key"),str) and isinstance(c.get("ok"),bool) for c in checks):
        raise RuntimeError("Malformed readiness response")
    checks_by_key={c["key"]:c for c in checks}
    for key in ("app_environment","authentication_provider","payment_provider","file_storage","kyc_provider","legal_review"):
        if key not in checks_by_key:
            raise RuntimeError(f"Missing required readiness contract: {key}")
    # PR CI reads the *previous* deployed sandbox before this branch goes live.
    # It may lack the new payout gate; a true commercial check cannot omit it.
    if commercial and "marketplace_payout_settlement" not in checks_by_key:
        raise RuntimeError("Commercial readiness contract lacks verified marketplace payouts")
    # Privacy deletion currently retains email credentials in some cases.
    # Do not allow an otherwise healthy payments/provider state to disguise
    # this as a safe commercial release. A future reviewed server release must
    # expose an explicit positive privacy-deletion readiness check.
    if commercial and not checks_by_key.get("privacy_account_deletion",{}).get("ok",False):
        raise RuntimeError("Commercial launch blocked: account-deletion privacy review incomplete")
    cats=fetch(root,"/api/v1/categories").get("items")
    services=fetch(root,"/api/v1/services").get("items")
    if not isinstance(cats,list) or not isinstance(services,list) or len(cats)<5 or len(services)<40:
        raise RuntimeError("Existing service catalog unexpectedly missing or incomplete")
    category_ids={c.get("id") for c in cats}
    if any(not s.get("id") or not s.get("name_ar") or s.get("category_id") not in category_ids for s in services):
        raise RuntimeError("Invalid service or orphaned category in catalog")
    auth=fetch(root,"/api/v1/auth/account-status")
    if auth.get("registration")!="email_link" or auth.get("fields")!=["name","email","phone","password"]:
        raise RuntimeError("Verified email account contract missing")
    fetch(root,"/api/v1/me",expect=401)
    check_public_ui(root)
    failed=[c["key"] for c in checks if c.get("required") and not c["ok"]]
    print(f"MINJAZ {root} | health=OK catalog={len(services)} categories={len(cats)} public_ui=OK")
    print(f"Email signup enabled={auth.get('enabled')!s} configured={auth.get('configured')!s}")
    print(f"Required commercial blockers ({len(failed)}): {', '.join(failed) if failed else 'none'}")
    if commercial:
        if not readiness.get("ready_for_commercial_launch") or failed:
            raise RuntimeError("Commercial launch blocked; cannot advertise real payments or payouts")
        if not auth.get("enabled") or not auth.get("configured"):
            raise RuntimeError("Commercial launch blocked: verified email not live")
    return readiness

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base",default=DEFAULT_BASE)
    parser.add_argument("--commercial",action="store_true")
    args=parser.parse_args()
    try:run(args.base,args.commercial)
    except (RuntimeError,ValueError,KeyError,urllib.error.URLError,TimeoutError) as err:
        print(f"FAIL: {err}",file=sys.stderr);return 1
    return 0

if __name__=="__main__":sys.exit(main())
