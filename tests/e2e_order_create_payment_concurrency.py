import json, os, random, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
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
    assert out.get("token"),out
    return out

def run():
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    base=int(time.time())%90000000+10000000
    phones=[f"+9665{base+i:08d}" for i in range(3)]

    client=login(phones[0],"client","Order Race Client")
    f1=login(phones[1],"freelancer","Order Race Freelancer A")
    f2=login(phones[2],"freelancer","Order Race Freelancer B")
    ct,t1,t2=client["token"],f1["token"],f2["token"]

    task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سباق قبول العروض والدفع",
        "description":"اختبار آلي للتأكد من إنشاء طلب واحد فقط ومنع تكرار أثر الدفع عند الطلبات المتزامنة.",
        "budget_min":"100","budget_max":"200","urgency":"normal"
    },ct)

    p1=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"120.00","delivery_hours":24,"revisions":1,"message":"عرض A"
    },t1)
    p2=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"125.00","delivery_hours":24,"revisions":1,"message":"عرض B"
    },t2)

    barrier=Barrier(2)
    def accept(item):
        label,pid=item
        barrier.wait()
        return label,raw_call("POST","/api/v1/orders",{"proposal_id":pid},ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        created=list(ex.map(accept,[("a",p1["id"]),("b",p2["id"])]))

    assert sorted(x[1][0] for x in created)==[201,409],created
    winner_label,winner_http=next((label,res) for label,res in created if res[0]==201)
    loser_payload=next(res[1] for label,res in created if res[0]==409)
    assert loser_payload.get("error")=="order_exists",loser_payload
    order=winner_http[1]

    orders=call("GET","/api/v1/orders",token=ct,expected=(200,)).get("items") or []
    same_task=[x for x in orders if int(x["task_id"])==int(task["id"])]
    assert len(same_task)==1,same_task
    assert int(same_task[0]["id"])==int(order["id"]),same_task

    repeat_pid=p1["id"] if winner_label=="a" else p2["id"]
    repeat=raw_call("POST","/api/v1/orders",{"proposal_id":repeat_pid},ct)
    assert repeat[0]==409 and repeat[1].get("error")=="order_exists",repeat

    pay_barrier=Barrier(2)
    def pay(_):
        pay_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        payments=list(ex.map(pay,(1,2)))

    assert [x[0] for x in payments]==[200,200],payments
    assert sum(1 for _,p in payments if p.get("already_paid"))==1,payments
    assert sum(1 for _,p in payments if p.get("mode")=="mock" and not p.get("already_paid"))==1,payments

    final_order=call("GET",f"/api/v1/orders/{order['id']}",token=ct,expected=(200,))
    assert final_order["status"]=="in_progress" and final_order["payment_status"]=="paid",final_order

    timeline=call("GET",f"/api/v1/orders/{order['id']}/timeline",token=ct,expected=(200,)).get("items") or []
    payment_events=[x for x in timeline if x.get("type")=="payment"]
    assert len(payment_events)==1,payment_events

    winner_token=t1 if int(order["freelancer_id"])==int(f1["user"]["id"]) else t2
    notes=call("GET","/api/v1/notifications?kind=payment&limit=50",token=winner_token,expected=(200,)).get("items") or []
    payment_notes=[x for x in notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(payment_notes)==1,payment_notes

    return {
        "ok":True,"version":health.get("version"),
        "single_order_under_concurrency":True,
        "stable_order_conflict":True,
        "mock_payment_idempotent":True,
        "single_payment_event":True,
        "single_payment_notification":True,
        "order_id":order["id"],"task_id":task["id"],"winning_proposal":winner_label
    }

RESULT=run()
print("MINJAZ_ORDER_CREATE_PAYMENT_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)
if os.getenv("E2E_EXIT_AFTER_RUN")=="1":
    raise SystemExit(0)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
