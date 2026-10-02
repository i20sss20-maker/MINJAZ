import json, os, random, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
ADMIN_PHONE=os.getenv("E2E_ADMIN_PHONE","").strip()
PORT=int(os.getenv("PORT","3000"))

def raw_call(method,path,body=None,token=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None:headers["Content-Type"]="application/json"
    if token:headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            status=r.status;raw=r.read()
    except urllib.error.HTTPError as e:
        status=e.code;raw=e.read()
    try:payload=json.loads(raw or b"{}")
    except Exception:payload={"raw":raw.decode(errors="replace")}
    return status,payload

def call(method,path,body=None,token=None,expected=(200,201)):
    status,payload=raw_call(method,path,body,token)
    assert status in expected,(method,path,status,payload)
    return payload

def login(phone,role,name):
    for attempt in range(3):
        status,ch=raw_call("POST","/api/v1/auth/request-otp",{"phone":phone})
        if status==201:break
        if status==429 and attempt<2:
            time.sleep(min(65,int(ch.get("retry_after_seconds") or 60)+1));continue
        raise AssertionError(("otp_request",status,ch))
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{
        "challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name
    })
    assert out.get("token") and out["user"]["role"]==role,out
    return out

def create_paid_order(ct,ft,category_id,title,price="120.00"):
    task=call("POST","/api/v1/tasks",{
        "category_id":category_id,"title":title,
        "description":"اختبار آلي للتأكد من سلامة القرارات الإدارية المتزامنة في حالات النزاع والإلغاء.",
        "budget_min":"100","budget_max":"180","urgency":"normal"
    },ct)
    proposal=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":price,"delivery_hours":24,"revisions":2,"message":"عرض اختبار سباق قرار إداري."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":proposal["id"]},ct)
    paid=call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    assert paid.get("ok") is True and paid.get("mode")=="mock",paid
    return task,order

def concurrent_admin(path,payloads,token):
    barrier=Barrier(len(payloads))
    def run_one(item):
        label,body=item
        barrier.wait()
        return label,raw_call("PATCH",path,body,token)
    with ThreadPoolExecutor(max_workers=len(payloads)) as ex:
        return list(ex.map(run_one,payloads))

def run():
    assert ADMIN_PHONE,"E2E_ADMIN_PHONE is required"
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    cat=cats[0]["id"]
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"

    client=login("+9665"+seed,"client","Case Race Client")
    freelancer=login("+9667"+seed,"freelancer","Case Race Freelancer")
    admin=login(ADMIN_PHONE,"admin","Case Race Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]

    # Dispute: resume vs cancel at the same moment.
    task1,order1=create_paid_order(ct,ft,cat,"اختبار سباق قرار النزاع")
    dispute=call("POST",f"/api/v1/orders/{order1['id']}/dispute",{
        "reason":"اختبار سباق النزاع","details":"قراران إداريان متعارضان يجب ألا يكتبا فوق بعضهما."
    },ct)

    dispute_results=concurrent_admin(
        f"/api/admin/disputes/{dispute['id']}",
        [
            ("resume",{"status":"resolved","action":"resume","resolution_note":"قرار متزامن resume"}),
            ("cancel",{"status":"resolved","action":"cancel","resolution_note":"قرار متزامن cancel"})
        ],
        at
    )
    assert sorted(x[1][0] for x in dispute_results)==[200,409],dispute_results
    winning_dispute=next(label for label,(http,payload) in dispute_results if http==200)
    losing_dispute=next(payload for label,(http,payload) in dispute_results if http==409)
    assert losing_dispute.get("error")=="dispute_finalized",losing_dispute

    final_order1=call("GET",f"/api/v1/orders/{order1['id']}",token=ct,expected=(200,))
    final_task1=call("GET",f"/api/v1/tasks/{task1['id']}",token=ct,expected=(200,))
    disputes=call("GET","/api/admin/disputes",token=at,expected=(200,)).get("items") or []
    drow=next(x for x in disputes if int(x["id"])==int(dispute["id"]))
    assert drow["status"]=="resolved" and drow["resolution_action"]==winning_dispute,drow
    if winning_dispute=="resume":
        assert final_order1["status"]=="in_progress" and final_order1["payment_status"]=="paid",final_order1
        assert final_task1["status"]=="in_progress",final_task1
    else:
        assert final_order1["status"]=="cancelled" and final_order1["payment_status"]=="refunded",final_order1
        assert final_task1["status"]=="cancelled",final_task1

    repeat_dispute=raw_call("PATCH",f"/api/admin/disputes/{dispute['id']}",{
        "status":"resolved","action":winning_dispute,"resolution_note":"repeat final"
    },at)
    assert repeat_dispute[0]==409 and repeat_dispute[1].get("error")=="dispute_finalized",repeat_dispute

    # Cancellation: approve vs reject at the same moment.
    task2,order2=create_paid_order(ct,ft,cat,"اختبار سباق قرار الإلغاء","130.00")
    cancel=call("POST",f"/api/v1/orders/{order2['id']}/cancellation",{
        "reason":"اختبار سباق الإلغاء","details":"اعتماد ورفض متزامنان؛ يجب تثبيت قرار واحد فقط."
    },ct)

    cancel_results=concurrent_admin(
        f"/api/admin/cancellations/{cancel['id']}",
        [
            ("approved",{"status":"approved","admin_note":"قرار متزامن اعتماد"}),
            ("rejected",{"status":"rejected","admin_note":"قرار متزامن رفض"})
        ],
        at
    )
    assert sorted(x[1][0] for x in cancel_results)==[200,409],cancel_results
    winning_cancel=next(label for label,(http,payload) in cancel_results if http==200)
    losing_cancel=next(payload for label,(http,payload) in cancel_results if http==409)
    assert losing_cancel.get("error")=="cancellation_finalized",losing_cancel

    final_cancel=call("GET",f"/api/v1/orders/{order2['id']}/cancellation",token=ct,expected=(200,))["item"]
    final_order2=call("GET",f"/api/v1/orders/{order2['id']}",token=ct,expected=(200,))
    final_task2=call("GET",f"/api/v1/tasks/{task2['id']}",token=ct,expected=(200,))
    assert final_cancel["status"]==winning_cancel,final_cancel
    if winning_cancel=="approved":
        assert final_order2["status"]=="cancelled" and final_order2["payment_status"]=="refunded",final_order2
        assert final_task2["status"]=="cancelled",final_task2
    else:
        assert final_order2["status"]=="in_progress" and final_order2["payment_status"]=="paid",final_order2
        assert final_task2["status"]=="in_progress",final_task2

    repeat_cancel=raw_call("PATCH",f"/api/admin/cancellations/{cancel['id']}",{
        "status":winning_cancel,"admin_note":"repeat final"
    },at)
    assert repeat_cancel[0]==409 and repeat_cancel[1].get("error")=="cancellation_finalized",repeat_cancel

    return {
        "ok":True,"version":health.get("version"),
        "dispute_concurrency":True,
        "cancellation_concurrency":True,
        "dispute_finality":True,
        "cancellation_finality":True,
        "winning_dispute_action":winning_dispute,
        "winning_cancellation_action":winning_cancel,
        "dispute_order_id":order1["id"],
        "cancellation_order_id":order2["id"]
    }

RESULT=run()
print("MINJAZ_CASE_CONCURRENCY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN","").strip()=="1":
    raise SystemExit(0)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
