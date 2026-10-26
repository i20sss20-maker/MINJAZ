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
    for item in services:
        if not isinstance(item, dict) or not isinstance(item.get("slug"), str) or not item.get("title_ar"):
            raise AssertionError("catalog contains an incomplete package")
        if "price_sar" not in item or "delivery_days" not in item:
            raise AssertionError("catalog package missing essential fields")
    # The administrator may hide any demo package. Hidden services must remain
    # absent from the public catalog and cannot be required by this smoke test.
    demo_slugs = {"website-starter-demo", "ecommerce-starter-demo", "branding-starter-demo"}
    visible = {item["slug"] for item in services if item["slug"] in demo_slugs}
    print(f"PASS public catalog structure; {len(services)} visible services; {len(visible)} demo packages currently visible")
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
