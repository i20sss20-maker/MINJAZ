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
    for attempt in range(2):
        try:
            ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
            break
        except AssertionError as exc:
            info=exc.args[0] if exc.args else ()
            if attempt==0 and isinstance(info,tuple) and len(info)>=3 and info[1]==429:
                delay=min(65,int((info[2] or {}).get("retry_after_seconds") or 60)+1)
                time.sleep(delay)
                continue
            raise
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name})
    assert out.get("token") and out["user"]["role"]==role,out
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

    sessions=call("GET","/api/v1/account/sessions",token=ct,expected=(200,))
    assert sessions.get("items") and any(x.get("current") for x in sessions["items"]),sessions

    # Completed order -> earnings -> KYC -> payout lifecycle.
    task1,order1=create_order(ct,ft,cat,"اختبار أرباح وسحب")
    call("POST",f"/api/v1/orders/{order1['id']}/deliver",{"note":"تسليم اختبار الأرباح."},ft)
    call("POST",f"/api/v1/orders/{order1['id']}/complete",{},ct)
    earnings=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    assert float(earnings.get("available_balance") or 0)>0,earnings
    call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"approved"},at,expected=(200,))
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
    ticket=call("POST","/api/v1/support/tickets",{
        "category":"technical","subject":"اختبار الدعم","message":"تذكرة اختبار آلي للتحقق من لوحة الدعم.","priority":"normal"
    },ct)
    tickets=call("GET","/api/admin/support",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(ticket["id"]) for x in tickets)
    tres=call("PATCH",f"/api/admin/support/{ticket['id']}",{
        "status":"resolved","admin_reply":"تمت معالجة تذكرة الاختبار."
    },at,expected=(200,))
    assert tres["status"]=="resolved",tres

    # Privacy.
    privacy=call("POST","/api/v1/privacy/requests",{
        "request_type":"access","details":"طلب اختبار آلي لحقوق الوصول للبيانات."
    },ct)
    plist=call("GET","/api/admin/privacy",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(privacy["id"]) for x in plist)
    pres=call("PATCH",f"/api/admin/privacy/{privacy['id']}",{
        "status":"completed","admin_note":"تم اختبار معالجة طلب الخصوصية."
    },at,expected=(200,))
    assert pres["status"]=="completed",pres

    # Safety report review without punitive moderation.
    safety=call("POST","/api/v1/safety/reports",{
        "category":"other","details":"بلاغ اختبار آلي للتحقق من مسار الأمان والمراجعة الإدارية.",
        "order_id":order3["id"]
    },ft)
    slist=call("GET","/api/admin/safety/reports",token=at,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(safety["id"]) for x in slist)
    sres=call("PATCH",f"/api/admin/safety/reports/{safety['id']}",{
        "status":"dismissed","admin_note":"بلاغ اختبار فقط ولا يتطلب إجراء."
    },at,expected=(200,))
    assert sres["status"]=="dismissed",sres

    summary=call("GET","/api/admin/summary",token=at,expected=(200,))
    operations=call("GET","/api/admin/operations",token=at,expected=(200,))
    assert "users" in summary and "metrics" in operations and "operational" in operations

    return {
        "ok":True,"version":health.get("version"),
        "admin_auth":True,"sessions":True,"payout_lifecycle":True,
        "cancellation_refund":True,"dispute_resume":True,
        "support_admin":True,"privacy_admin":True,"safety_admin":True,
        "admin_summary":True,"admin_operations":True,
        "completed_order_id":order1["id"],"cancelled_order_id":order2["id"],
        "disputed_order_id":order3["id"],"payout_id":payout_id
    }

RESULT=run()
print("MINJAZ_OPERATIONS_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

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
