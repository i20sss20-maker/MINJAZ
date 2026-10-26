#!/usr/bin/env python3
"""PostgreSQL contract test for the complete MINJAZ digital-services preview workflow.

Runs only in GitHub Actions against a fresh local 'digital_test' database.
Never reads Railway DATABASE_URL or any production credentials.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from urllib.parse import urlparse
import sys

# Running as a file puts scripts/ first on sys.path, not the repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg2
from minjaz_digital_services import dispatch as customer
from minjaz_digital_workflow import dispatch as workflow, SANDBOX_PROJECT_ID
from scripts.seed_digital_services_preview import seed_packages
TEST_URL = os.getenv("DIGITAL_TEST_DATABASE_URL", "")
CUSTOMER = {"id":11,"role":"customer"}
ADMIN = {"id":22,"role":"admin"}
OTHER = {"id":33,"role":"customer"}
ORDER = "/api/digital-services/orders"
ADMIN_ROUTE = "/api/digital-services/admin"

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def guarded_connect():
    """An exact local database guard is required before any write can happen."""
    parsed = urlparse(TEST_URL)
    if (os.getenv("CI","").lower() != "true" or parsed.scheme not in ("postgres","postgresql")
        or parsed.hostname not in ("localhost","127.0.0.1") or parsed.port != 5432
        or parsed.path != "/digital_test" or parsed.username != "postgres"):
        raise RuntimeError("Refusing integration test outside ephemeral local CI PostgreSQL")
    return psycopg2.connect(TEST_URL, connect_timeout=5)

def setup():
    with guarded_connect() as db:
        with db.cursor() as cur:
            cur.execute("CREATE TABLE users (id BIGINT PRIMARY KEY)")
            cur.execute("INSERT INTO users(id) VALUES (11),(22),(33)")
        for name in (
            "025_digital_services.sql",
            "026_digital_service_revisions.sql",
            "027_order_revision_snapshot.sql",
            "028_customer_foreign_key.sql",
            "029_digital_service_fulfillment.sql",
            "030_digital_service_package_audit.sql",
            "031_digital_service_order_idempotency.sql",
        ):
            # Each migration wraps its statements in BEGIN/COMMIT.
            with db.cursor() as cur:
                cur.execute((ROOT/"database"/"migrations"/name).read_text(encoding="utf-8"))
            print("PASS migration",name)
        with db.cursor() as cur:
            counts=seed_packages(cur)
            check(counts=={"present":3,"active":3,"hidden":0},"initial seed inconsistent")
        print("PASS initial sandbox demo seed")

def call_customer(method,path,body=None,actor=CUSTOMER):
    return customer(method,path,{},body,actor,guarded_connect)

def call_workflow(method,path,body=None,actor=ADMIN):
    return workflow(method,path,{},body,actor,guarded_connect)

def run():
    setup()
    # Workflow mutations are guarded by this exact project ID and payment_mode.
    os.environ.update({"APP_ENV":"preview","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,
                       "PAYMENT_MODE":"mock"})
    code,catalog=call_customer("GET","/api/digital-services/catalog")
    check(code==200 and len(catalog["services"])==3,"initial catalog is not public")
    filtered_code,filtered=customer("GET","/api/digital-services/catalog",
                                   {"category":["website"]},None,None,guarded_connect)
    check(filtered_code==200 and len(filtered["services"])==1
          and filtered["services"][0]["category"]=="website",
          "category query did not filter on the database")
    package=next(item for item in catalog["services"] if item["slug"]=="website-starter-demo")
    package_id=package["id"]

    data={"package_id":package_id,"requirements":"موقع تعريفي عربي للعمل مع صفحات الخدمات والتواصل.",
          "idempotency_key":"ci-digital-order-unique-0001"}
    code,new=call_customer("POST",ORDER,data)
    check(code==201 and new["status"]=="draft","order was not created")
    order_id=new["order_id"]
    code,replayed=call_customer("POST",ORDER,data)
    check(code==200 and replayed["order_id"]==order_id
          and replayed["idempotent_replay"],"order idempotency replay failed")
    altered={**data,"requirements":data["requirements"]+" تغيير المحتوى"}
    check(call_customer("POST",ORDER,altered)[0]==409,"reused key with new body accepted")
    code,owner=call_customer("GET",ORDER+"/"+str(order_id))
    check(code==200 and owner["order"]["price_sar"]=="1499.00",
          "original agreed-price snapshot was not stored")
    check(call_customer("GET",ORDER+"/"+str(order_id),actor=OTHER)[0]==404,
          "other customer accessed private order")
    check(call_workflow("GET",ADMIN_ROUTE+"/orders",actor=OTHER)[0]==403,
          "non-admin listed customer orders")
    edited_requirements="تم تعديل متطلبات الموقع لإضافة صفحة معرض أعمال وقسم أسئلة شائعة."
    code,changed=call_customer("PATCH",ORDER+"/"+str(order_id),
                               {"requirements":edited_requirements})
    check(code==200 and changed["requirements"]==edited_requirements,
          "customer could not update draft requirements")
    check(call_customer("PATCH",ORDER+"/"+str(order_id),
                        {"requirements":"محاولة تعديل من عميل غير مالك"},OTHER)[0]==404,
          "another customer updated the draft")
    print("PASS owner privacy, frozen pricing, draft edit and idempotent submission")

    def admin_to(state,note=""):
        code,payload=call_workflow("PATCH",ADMIN_ROUTE+"/orders/"+str(order_id),
                                   {"status":state,"note":note})
        check(code==200, f"admin transition to {state} failed: {payload}")
    def customer_to(action,note=None):
        body={"note":note} if note else {}
        code,payload=call_workflow("POST",ORDER+"/"+str(order_id)+"/"+action,body,CUSTOMER)
        check(code==200, f"customer action {action} failed: {payload}")

    check(call_workflow("PATCH",ADMIN_ROUTE+"/orders/"+str(order_id),
          {"status":"delivered","note":"ملفات التسليم جاهزة للعميل"})[0]==409,
          "admin skipped from draft to delivered")
    admin_to("in_progress")
    check(call_customer("PATCH",ORDER+"/"+str(order_id),
          {"requirements":"لا يجب تعديل المشروع بعد بدء التنفيذ"})[0]==409,
          "started order requirements were changed")
    admin_to("delivered","تم إعداد الموقع وتسليم ملفات النسخة الأولى")
    customer_to("revisions","يرجى تعديل ألوان الصفحة الرئيسية إلى الأزرق")
    admin_to("in_progress")
    admin_to("delivered","تم تحديث الألوان وتسليم النسخة الثانية")
    customer_to("revisions","يرجى تحسين حجم النص في الصفحة الرئيسية")
    admin_to("in_progress")
    admin_to("delivered","تم تعديل حجم النص وتسليم النسخة النهائية")
    code,blocked=call_workflow("POST",ORDER+"/"+str(order_id)+"/revisions",
              {"note":"طلب تعديل ثالث يتجاوز العدد المتاح"},CUSTOMER)
    check(code==409 and blocked["error"]=="revision_limit_reached",
          "agreed revision limit not enforced")
    customer_to("complete")
    check(call_workflow("POST",ORDER+"/"+str(order_id)+"/cancel",{},CUSTOMER)[0]==409,
          "completed order could be cancelled")
    code,result=call_customer("GET",ORDER+"/"+str(order_id))
    check(code==200 and result["order"]["status"]=="completed"
          and result["order"]["revisions_used"]==2
          and len(result["order"]["events"])==11,
          "full order audit timeline is incomplete")
    print("PASS complete delivery lifecycle, two revisions, final acceptance and audit")

    code,pkg=call_workflow("PATCH",ADMIN_ROUTE+"/packages/"+str(package_id),
                           {"active":False})
    check(code==200 and not pkg["package"]["active"],"admin cannot hide demo package")
    code,visible=call_customer("GET","/api/digital-services/catalog")
    check(code==200 and not any(x["id"]==package_id for x in visible["services"]),
          "hidden package leaked to public catalog")
    with guarded_connect() as db:
        with db.cursor() as cur:
            counts=seed_packages(cur)
    check(counts["hidden"]==1 and counts["active"]==2,
          "redeployment seed ignored admin-hidden package")
    call_workflow("PATCH",ADMIN_ROUTE+"/packages/"+str(package_id),
                  {"active":True,"price_sar":"1599.00"})
    code,result=call_customer("GET",ORDER+"/"+str(order_id))
    check(code==200 and result["order"]["price_sar"]=="1499.00",
          "package price editing changed historical agreed pricing")

    details={"slug":"ci-digital-custom","category":"ai","title_ar":"خدمة تجريبية ضمن CI",
             "description_ar":"خدمة جديدة للتحقق من إنشاء الباقات", "price_sar":"45.00",
             "delivery_days":3,"revision_limit":1,"active":False}
    code,created=call_workflow("POST",ADMIN_ROUTE+"/packages",details)
    check(code==201 and created["package"]["slug"]=="ci-digital-custom",
          "admin package creation failed")
    code,history=call_workflow("GET",ADMIN_ROUTE+"/packages/"+str(package_id)+"/events")
    check(code==200 and len(history["events"])==2,
          "package updates were not audited")
    code,summary=call_workflow("GET",ADMIN_ROUTE+"/summary")
    check(code==200 and summary["by_status"].get("completed")==1
          and summary["active_packages"]==3,"admin dashboard summary incorrect")
    print("PASS package creation, visibility, admin audit and summary")

    # Five simultaneous network-like retries should commit one draft only.
    concurrent={"package_id":package_id,"requirements":data["requirements"],
                "idempotency_key":"ci-digital-concurrent-0000002"}
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses=list(pool.map(lambda _:call_customer("POST",ORDER,concurrent),range(5)))
    ids={v["order_id"] for status,v in responses if status in (200,201)}
    check(len(ids)==1 and sum(status==201 for status,v in responses)==1
          and all(status in (200,201) for status,v in responses),
          "concurrent client retries caused duplicate orders: "+repr(responses))
    with guarded_connect() as db:
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM digital_service_order_events WHERE order_id=%s",(next(iter(ids)),))
            check(cur.fetchone()[0]==1,"repeated submission created duplicate audit events")
            cur.execute("SELECT COUNT(*) FROM digital_service_orders WHERE payment_reference IS NOT NULL")
            check(cur.fetchone()[0]==0,"integration run unexpectedly recorded a payment reference")
    print("PASS concurrent retries result in exactly one draft, one audit event and no payment")
    print("PASS full PostgreSQL preview-only contract test")

if __name__=="__main__":
    run()
