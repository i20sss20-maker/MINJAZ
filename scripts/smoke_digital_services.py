#!/usr/bin/env python3
"""Read-only smoke checks for MINJAZ sandbox. Never creates accounts or orders."""
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = os.getenv("MINJAZ_SMOKE_URL", "https://minjaz-digital-services-api-sandbox.up.railway.app").rstrip("/")

def check(path, expected, key=None):
    req=Request(BASE+path,headers={"Accept":"application/json","User-Agent":"MINJAZ-sandbox-smoke/1"})
    try:
        with urlopen(req,timeout=15) as response:
            status=response.status
            body=response.read(131072)
    except HTTPError as error:
        status=error.code
        body=error.read(131072)
    data=json.loads(body.decode("utf-8")) if body else {}
    if status!=expected or (key is not None and key not in data):
        raise AssertionError(f"{path}: expected {expected} and key {key}, got {status} {str(data)[:250]}")
    print(f"PASS {path}: HTTP {status}")
    return data

def check_html(path, marker):
    req = Request(BASE+path,headers={"Accept":"text/html","User-Agent":"MINJAZ-sandbox-smoke/1"})
    with urlopen(req,timeout=15) as response:
        status=response.status
        content_type=response.headers.get("Content-Type","")
        html=response.read(524288).decode("utf-8")
    if status != 200 or "text/html" not in content_type.lower() or marker not in html:
        raise AssertionError(f"{path}: page or marker missing (HTTP {status})")
    print(f"PASS {path}: HTML page ready")

def main():
    catalog = check("/api/digital-services/catalog",200,"services")
    services = catalog["services"]
    if not isinstance(services, list):
        raise AssertionError("catalog.services must be an array")
    expected_slugs = {"website-starter-demo", "ecommerce-starter-demo", "branding-starter-demo"}
    actual_slugs = {item.get("slug") for item in services if isinstance(item, dict)}
    missing = expected_slugs - actual_slugs
    if missing:
        raise AssertionError(f"missing active demo packages from public catalog: {sorted(missing)}")
    print(f"PASS public catalog contains all {len(expected_slugs)} demo packages")
    check("/api/digital-services/catalog?category=unknown",400,"error")
    check("/api/digital-services/orders",401,"error")
    check("/api/digital-services/orders/1",401,"error")
    check("/api/digital-services/admin/orders",401,"error")
    check("/api/digital-services/admin/packages",401,"error")
    check("/api/digital-services/admin/summary",401,"error")
    check_html("/digital-services","خدمات منجاز الرقمية")
    check("/api/digital-services/orders/1/revisions",401,"error")
    check("/digital-services/admin",401,"error")
    check("/health",200,"ok")
    print("All read-only sandbox checks passed.")

if __name__=="__main__":
    try: main()
    except (AssertionError,URLError,ValueError,TimeoutError) as error:
        print(f"FAIL: {error}",file=sys.stderr)
        sys.exit(1)
