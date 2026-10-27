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

def run(base,commercial=False):
    url=urlparse(base)
    if url.scheme!="https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise RuntimeError("HTTPS base URL without credentials or query required")
    root=base.rstrip("/")
    health=fetch(root,"/health")
    if health.get("ok") is not True or health.get("database") is not True:
        raise RuntimeError("Health/database is not healthy")
    readiness=fetch(root,"/readiness")
    checks=readiness.get("checks")
    if not isinstance(checks,list) or not all(isinstance(c,dict) and isinstance(c.get("key"),str) and isinstance(c.get("ok"),bool) for c in checks):
        raise RuntimeError("Malformed readiness response")
    checks_by_key={c["key"]:c for c in checks}
    for key in ("app_environment","authentication_provider","payment_provider","file_storage","kyc_provider","legal_review","marketplace_payout_settlement"):
        if key not in checks_by_key:
            raise RuntimeError(f"Missing required readiness contract: {key}")
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
    failed=[c["key"] for c in checks if c.get("required") and not c["ok"]]
    print(f"MINJAZ {root} | health=OK catalog={len(services)} categories={len(cats)}")
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
