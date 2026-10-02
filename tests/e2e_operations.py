import json, os, random, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
ADMIN_PHONE=os.getenv("E2E_ADMIN_PHONE","").strip()
PORT=int(os.getenv("PORT","3000"))

def call(method,path,body=None,token=None,expected=(200,201)):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            payload=json.loads(r.read() or b"{}")
            assert r.status in expected,(path,r.status,payload)
            return payload
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: payload=json.loads(raw or b"{}")
        except Exception: payload={"raw":raw.decode(errors="replace")}
        raise AssertionError((path,e.code,payload)) from e

def login(phone,role,name):
    if not phone: raise AssertionError("missing_phone")
    for attempt in range(3):
        try:
            ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
            break
        except AssertionError as exc:
            info=exc.args[0] if exc.args else ()
            if attempt<2 and isinstance(info,tuple) and len(info)>=3 and info[1]==429:
                delay=min(65,int((info[2] or {}).get("retry_after_seconds") or 60)+1)
                time.sleep(delay)
                continue
            raise
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name})
    effective_roles=out.get("roles") or out.get("user",{}).get("roles") or [out.get("user",{}).get("role")]
    assert out.get("token") and role in effective_roles,out
    return out

def create_order(ct,ft,category_id,title,price=120):
    task=call("POST","/api/v1/tasks",{
        "category_id":category_id,"title":title,
        "description":"اختبار آلي تشغيلي متقدم لمنصة منجاز للتحقق من الحالات الإدارية ودورة الطلبات.",
        "budget_min":100,"budget_max":180,"urgency":"normal"
    },ct)
    prop=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":price,"delivery_hours":24,"revisions":2,"message":"عرض آلي لاختبار العمليات."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":prop["id"]},ct)
    paid=call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    assert paid.get("ok") is True and paid.get("mode")=="mock",paid
    return task,order

def run():
    assert ADMIN_PHONE,"E2E_ADMIN_PHONE is required"
    health=call("GET","/health",expected=(200,))
    assert health.get("ok") is True and health.get("database") is True,health
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats,"categories_empty"
    cat=cats[0]["id"]

    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    client=login("+9665"+seed,"client","Ops E2E Client")
    freelancer=login("+9667"+seed,"freelancer","Ops E2E Freelancer")
    admin=login(ADMIN_PHONE,"admin","MINJAZ Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]
    fid=freelancer["user"]["id"]
    docs={"documents":["terms","privacy","marketplace_rules"]}
    assert call("POST","/api/v1/legal/accept",docs,ct,expected=(200,)).get("complete") is True
    assert call("POST","/api/v1/legal/accept",docs,ft,expected=(200,)).get("complete") is True

    sessions=call("GET","/api/v1/account/sessions",token=ct,expected=(200,))
    assert sessions.get("items") and any(x.get("current") for x in sessions["items"]),sessions

    # Completed order -> earnings -> KYC -> payout lifecycle.
    task1,order1=create_order(ct,ft,cat,"اختبار أرباح وسحب")
    call("POST",f"/api/v1/orders/{order1['id']}/deliver",{"note":"تسليم اختبار الأرباح."},ft)
    call("POST",f"/api/v1/orders/{order1['id']}/complete",{},ct)
    earnings=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    assert float(earnings.get("available_balance") or 0)>0,earnings
    kyc_update=call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"approved"},at,expected=(200,))
    assert kyc_update.get("idempotent_replay") is False,kyc_update
    kyc_retry=call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"approved"},at,expected=(200,))
    assert kyc_retry.get("idempotent_replay") is True,kyc_retry
    payout_amount=round(min(10.0,float(earnings["available_balance"])),2)
    payout=call("POST","/api/v1/freelancer/payouts",{"amount":payout_amount,"note":"اختبار دورة السحب"},ft)
    payout_id=payout["item"]["id"]
    admin_payouts=call("GET","/api/admin/payouts",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(payout_id) for x in admin_payouts)
    call("PATCH",f"/api/admin/payouts/{payout_id}",{"status":"processing","admin_note":"اختبار معالجة"},at,expected=(200,))
    paid_payout=call("PATCH",f"/api/admin/payouts/{payout_id}",{"status":"paid","admin_note":"اختبار تم التنفيذ"},at,expected=(200,))
    assert paid_payout["item"]["status"]=="paid",paid_payout

    # Cancellation + mock refund lifecycle.
    task2,order2=create_order(ct,ft,cat,"اختبار الإلغاء والاسترداد")
    cancel=call("POST",f"/api/v1/orders/{order2['id']}/cancellation",{
        "reason":"اختبار إلغاء","details":"التحقق من اعتماد الإلغاء والاسترداد في وضع الدفع التجريبي."
    },ct)
    cancels=call("GET","/api/admin/cancellations",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(cancel["id"]) for x in cancels)
    cres=call("PATCH",f"/api/admin/cancellations/{cancel['id']}",{
        "status":"approved","admin_note":"اعتماد اختبار الإلغاء"
    },at,expected=(200,))
    assert cres["status"]=="approved" and cres["refund_status"]=="refunded",cres
    cancelled_order=call("GET",f"/api/v1/orders/{order2['id']}",token=ct,expected=(200,))
    assert cancelled_order["status"]=="cancelled" and cancelled_order["payment_status"]=="refunded",cancelled_order

    # Dispute lifecycle and resume.
    task3,order3=create_order(ct,ft,cat,"اختبار النزاع والاستئناف")
    dispute=call("POST",f"/api/v1/orders/{order3['id']}/dispute",{
        "reason":"نزاع اختبار","details":"التحقق من فتح النزاع ومراجعته ثم استئناف الطلب."
    },ct)
    disputes=call("GET","/api/admin/disputes",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(dispute["id"]) for x in disputes)
    dres=call("PATCH",f"/api/admin/disputes/{dispute['id']}",{
        "status":"resolved","action":"resume","resolution_note":"استئناف الطلب بعد اختبار النزاع"
    },at,expected=(200,))
    assert dres["status"]=="resolved" and dres["resolution_action"]=="resume",dres
    resumed=call("GET",f"/api/v1/orders/{order3['id']}",token=ct,expected=(200,))
    assert resumed["status"]=="in_progress",resumed

    # Support.
    support_key=f"support-ops-{seed}"
    support_payload={
        "category":"technical","subject":"اختبار الدعم","message":"تذكرة اختبار آلي للتحقق من لوحة الدعم.","priority":"normal",
        "idempotency_key":support_key
    }
    ticket=call("POST","/api/v1/support/tickets",support_payload,ct,expected=(201,))
    ticket_retry=call("POST","/api/v1/support/tickets",support_payload,ct,expected=(200,))
    assert int(ticket_retry["id"])==int(ticket["id"]) and ticket_retry.get("idempotent_replay") is True,(ticket,ticket_retry)
    own_tickets=call("GET","/api/v1/support/tickets",token=ct,expected=(200,)).get("items") or []
    assert len([x for x in own_tickets if x.get("subject")=="اختبار الدعم"])==1,own_tickets
    tickets=call("GET","/api/admin/support",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(ticket["id"]) for x in tickets)
    tres=call("PATCH",f"/api/admin/support/{ticket['id']}",{
        "status":"resolved","admin_reply":"تمت معالجة تذكرة الاختبار."
    },at,expected=(200,))
    assert tres["status"]=="resolved" and tres.get("idempotent_replay") is False,tres
    tres_retry=call("PATCH",f"/api/admin/support/{ticket['id']}",{
        "status":"resolved","admin_reply":"تمت معالجة تذكرة الاختبار."
    },at,expected=(200,))
    assert tres_retry.get("idempotent_replay") is True,tres_retry

    # Privacy.
    privacy_key=f"privacy-ops-{seed}"
    privacy_payload={"request_type":"access","details":"طلب اختبار آلي لحقوق الوصول للبيانات.","idempotency_key":privacy_key}
    privacy=call("POST","/api/v1/privacy/requests",privacy_payload,ct,expected=(201,))
    privacy_retry=call("POST","/api/v1/privacy/requests",privacy_payload,ct,expected=(200,))
    assert int(privacy_retry["id"])==int(privacy["id"]) and privacy_retry.get("idempotent_replay") is True,(privacy,privacy_retry)
    own_privacy=call("GET","/api/v1/privacy/requests",token=ct,expected=(200,)).get("items") or []
    assert len([x for x in own_privacy if x.get("request_type")=="access"])==1,own_privacy
    plist=call("GET","/api/admin/privacy",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(privacy["id"]) for x in plist)
    pres=call("PATCH",f"/api/admin/privacy/{privacy['id']}",{
        "status":"completed","admin_note":"تم اختبار معالجة طلب الخصوصية."
    },at,expected=(200,))
    assert pres["status"]=="completed" and pres.get("idempotent_replay") is False,pres
    pres_retry=call("PATCH",f"/api/admin/privacy/{privacy['id']}",{
        "status":"completed","admin_note":"تم اختبار معالجة طلب الخصوصية."
    },at,expected=(200,))
    assert pres_retry.get("idempotent_replay") is True,pres_retry
    ops_after_retries=call("GET","/api/admin/operations",token=at,expected=(200,))
    audit=ops_after_retries.get("audit") or []
    support_audit=[x for x in audit if x.get("action")=="support_updated" and str(x.get("target_id"))==str(ticket["id"])]
    privacy_audit=[x for x in audit if x.get("action")=="privacy_request_updated" and str(x.get("target_id"))==str(privacy["id"])]
    kyc_audit=[x for x in audit if x.get("action")=="kyc_status_updated" and str(x.get("target_id"))==str(fid)]
    assert len(support_audit)==1,support_audit
    assert len(privacy_audit)==1,privacy_audit
    assert len(kyc_audit)==1,kyc_audit

    # Safety report review without punitive moderation.
    safety=call("POST","/api/v1/safety/reports",{
        "category":"other","details":"بلاغ اختبار آلي للتحقق من مسار الأمان والمراجعة الإدارية.",
        "order_id":order3["id"]
    },ft)
    slist=call("GET","/api/admin/safety/reports",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(safety["id"]) for x in slist)
    safety_patch={"status":"dismissed","admin_note":"بلاغ اختبار فقط ولا يتطلب إجراء."}
    sres=call("PATCH",f"/api/admin/safety/reports/{safety['id']}",safety_patch,at,expected=(200,))
    assert sres["status"]=="dismissed" and sres.get("idempotent_replay") is False,sres
    sres_retry=call("PATCH",f"/api/admin/safety/reports/{safety['id']}",safety_patch,at,expected=(200,))
    assert sres_retry.get("idempotent_replay") is True,sres_retry
    safety_actions=call("GET","/api/admin/safety/actions",token=at,expected=(200,)).get("items") or []
    report_actions=[x for x in safety_actions if int(x.get("report_id") or 0)==int(safety["id"]) and x.get("action")=="report_dismissed"]
    assert len(report_actions)==1,report_actions
    safety_notes=call("GET","/api/v1/notifications?kind=safety&limit=50",token=ft,expected=(200,)).get("items") or []
    resolved_notes=[x for x in safety_notes if int(x.get("order_id") or 0)==int(order3["id"]) and x.get("title")=="تم تحديث بلاغ الأمان"]
    assert len(resolved_notes)==1,resolved_notes

    summary=call("GET","/api/admin/summary",token=at,expected=(200,))
    operations=call("GET","/api/admin/operations",token=at,expected=(200,))
    assert "users" in summary and "metrics" in operations and "operational" in operations
    safety_audit=[x for x in (operations.get("audit") or []) if x.get("action")=="safety_report_updated" and str(x.get("target_id"))==str(safety["id"])]
    assert len(safety_audit)==1,safety_audit

    return {
        "ok":True,"version":health.get("version"),
        "admin_auth":True,"sessions":True,"payout_lifecycle":True,
        "cancellation_refund":True,"dispute_resume":True,
        "support_admin":True,"privacy_admin":True,"safety_admin":True,
        "safety_admin_retry_safe":True,
        "support_admin_retry_safe":True,"privacy_admin_retry_safe":True,
        "support_create_retry_idempotent":True,"privacy_create_retry_idempotent":True,
        "admin_summary":True,"admin_operations":True,
        "completed_order_id":order1["id"],"cancelled_order_id":order2["id"],
        "disputed_order_id":order3["id"],"payout_id":payout_id
    }

RESULT=run()
print("MINJAZ_OPERATIONS_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN")=="1":
    raise SystemExit(0)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_): pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()

# trigger configured operations E2E service
