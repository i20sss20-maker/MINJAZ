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

def check_html(path, markers):
    req = Request(BASE+path,headers={"Accept":"text/html","User-Agent":"MINJAZ-sandbox-smoke/1"})
    with urlopen(req,timeout=15) as response:
        status=response.status
        content_type=response.headers.get("Content-Type","")
        html=response.read(524288).decode("utf-8")
    required=(markers,) if isinstance(markers,str) else tuple(markers)
    missing=[marker for marker in required if marker not in html]
    if status != 200 or "text/html" not in content_type.lower() or missing:
        raise AssertionError(f"{path}: missing real UI contract {missing!r} (HTTP {status})")
    print(f"PASS {path}: HTML page ready")

def check_css(path, marker):
    req=Request(BASE+path,headers={"Accept":"text/css","User-Agent":"MINJAZ-sandbox-smoke/1"})
    with urlopen(req,timeout=15) as response:
        status=response.status
        content_type=response.headers.get("Content-Type","")
        style=response.read(131072).decode("utf-8")
    if status != 200 or "text/css" not in content_type.lower() or marker not in style:
        raise AssertionError(f"{path}: missing unified design CSS (HTTP {status})")
    print(f"PASS {path}: unified design CSS served")

def check_script(path, marker):
    req=Request(BASE+path,headers={"Accept":"application/javascript","User-Agent":"MINJAZ-sandbox-smoke/1"})
    with urlopen(req,timeout=15) as response:
        js=response.read(131072).decode("utf-8")
        status=response.status
        content_type=response.headers.get("Content-Type","")
    if status!=200 or "javascript" not in content_type.lower() or marker not in js:
        raise AssertionError(f"{path}: registration UI not served (HTTP {status})")
    print(f"PASS {path}: email signup UI ready")

def main():
    account=check("/api/v1/auth/account-status",200,"configured")
    if account.get("registration")!="email_link" or account.get("fields")!=["name","email","phone","password"]:
        raise AssertionError("verified account registration contract missing")
    check_script("/minjaz-account-registration-v1.js","/api/v1/auth/register")
    state=check("/api/v1/auth/email-status",200,"configured")
    if state.get("method")!="email" or not isinstance(state.get("configured"),bool):
        raise AssertionError("email login provider state missing")
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
    category_catalog = check("/api/digital-services/catalog?category=website",200,"services")
    if not all(item.get("category") == "website" for item in category_catalog["services"]):
        raise AssertionError("category filtering returned a different category")
    print("PASS category-filtered catalog")
    # Read-only verification for every supported category, including newly
    # launched offerings. Administrators may legitimately hide individual
    # packages, so verify shape and filtering, not an arbitrary count.
    categories=("website","mobile_app","ecommerce","branding","maintenance","ai",
                "marketing","seo","content","video","automation","data","security","consulting")
    all_ids={item["id"] for item in services}
    if len(all_ids)!=len(services):
        raise AssertionError("duplicate package ids in catalog")
    for category in categories:
        subset=check("/api/digital-services/catalog?category="+category,200,"services")["services"]
        if any(item.get("category")!=category or item.get("id") not in all_ids for item in subset):
            raise AssertionError(f"{category}: invalid public category filtering")
    # Two distinct catalogs: first-party packages curated by operational scope,
    # versus the broad categories/subcategories that any freelancer can offer.
    parents=check("/api/v1/categories",200,"items")["items"]
    specialties=check("/api/v1/services",200,"items")["items"]
    if len(parents)<35 or len({row.get("slug") for row in parents})<35:
        raise AssertionError("marketplace missing expected parent categories")
    parent_ids={row.get("id") for row in parents}
    real_specializations=[row for row in specialties if str(row.get("slug","")).startswith("market-")]
    if len(real_specializations)<200:
        raise AssertionError("marketplace subcategory hierarchy incomplete")
    if not all(item.get("category_id") in parent_ids and item.get("client_guidance")
               and item.get("freelancer_guidance") for item in real_specializations):
        raise AssertionError("subcategory missing parent or role-specific guidance")
    print(f"PASS marketplace: {len(parents)} parent categories, "
          f"{len(real_specializations)} guided subcategories; "
          f"{len(services)} first-party offerings currently visible")
    check("/api/digital-services/catalog?category=unknown",400,"error")
    check("/api/digital-services/orders",401,"error")
    check("/api/digital-services/activity",401,"error")
    check("/api/digital-services/notifications",401,"error")
    check("/api/digital-services/notifications/read",401,"error")
    check("/api/digital-services/orders/1",401,"error")
    check("/api/digital-services/admin/orders",401,"error")
    check("/api/digital-services/admin/packages",401,"error")
    check("/api/digital-services/admin/summary",401,"error")
    check("/api/digital-services/admin/orders/1/deliverables",401,"error")
    check("/api/digital-services/orders/1/deliverables",401,"error")
    # Validate the *real*, redesigned sandbox pages (not retired marketing copy).
    check_html("/digital-services",('id="catalog"','id="orderForm"','id="notifications"','id="notificationsBadge"',
                                   'href="/signup?auth=login&amp;next=digital-services"'))
    check("/api/digital-services/orders/1/revisions",401,"error")
    check_html("/digital-services/admin",('id="adminAccess"','id="adminDashboard"',
                                          'id="adminEmailForm"','id="adminDraftNotice"','id="adminViewDrafts"'))
    check_html("/",('id="hero-title"','href="/signup"','class="flow-card"'))
    check_html("/signup",('id="signup"','id="login"','id="recover"'))
    check_html("/login",('id="signup"','id="login"','/api/v1/auth/login-email'))
    check_html("/workspace",('id="workspace"','id="clientAction"','id="freelancerAction"','id="taskSubcategories"','id="freelancerSpecialty"','id="taskServiceFilter"'))
    check_css("/minjaz-signature.css","Alexandria")
    check_css("/minjaz-unified-ui-v1.css","MINJAZ Unified UI v1")
    check("/health",200,"ok")
    print("All read-only sandbox checks passed.")

if __name__=="__main__":
    try: main()
    except (AssertionError,URLError,ValueError,TimeoutError) as error:
        print(f"FAIL: {error}",file=sys.stderr)
        sys.exit(1)
