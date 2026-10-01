import json, os, random, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
PORT=int(os.getenv("PORT","3000"))

def raw_call(method,path,body=None,token=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            status=r.status; raw=r.read()
    except urllib.error.HTTPError as e:
        status=e.code; raw=e.read()
    try: payload=json.loads(raw or b"{}")
    except Exception: payload={"raw":raw.decode(errors="replace")}
    return status,payload

def call(method,path,body=None,token=None,expected=(200,201)):
    status,payload=raw_call(method,path,body,token)
    assert status in expected,(method,path,status,payload)
    return payload

def login(phone,role,name):
    ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
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
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    client=login("+9665"+seed,"client","Order Create Race Client")
    f1=login("+9666"+seed,"freelancer","Order Create Race F1")
    f2=login("+9667"+seed,"freelancer","Order Create Race F2")
    ct,t1,t2=client["token"],f1["token"],f2["token"]

    task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],
        "title":"اختبار اختيار عرضين متزامنين",
        "description":"اختبار آلي للتأكد من أن المهمة لا تنشئ أكثر من طلب واحد عند قبول عرضين في نفس اللحظة.",
        "budget_min":"100","budget_max":"220","urgency":"normal"
    },ct)
    p1=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"120.00","delivery_hours":24,"revisions":1,"message":"العرض الأول"
    },t1)
    p2=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"130.00","delivery_hours":24,"revisions":1,"message":"العرض الثاني"
    },t2)

    barrier=Barrier(2)
    def choose(item):
        label,pid=item
        barrier.wait()
        return label,raw_call("POST","/api/v1/orders",{"proposal_id":pid},ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        results=list(ex.map(choose,[("p1",p1["id"]),("p2",p2["id"])]))

    assert sorted(x[1][0] for x in results)==[201,409],results
    winner_label=next(label for label,(status,payload) in results if status==201)
    winner=next(payload for label,(status,payload) in results if status==201)
    loser=next(payload for label,(status,payload) in results if status==409)
    assert loser.get("error")=="order_exists",loser
    assert int(loser.get("order_id") or 0)==int(winner["id"]),loser

    orders=call("GET","/api/v1/orders",token=ct,expected=(200,)).get("items") or []
    task_orders=[x for x in orders if int(x["task_id"])==int(task["id"])]
    assert len(task_orders)==1,task_orders
    assert int(task_orders[0]["id"])==int(winner["id"]),task_orders

    task_after=call("GET",f"/api/v1/tasks/{task['id']}",token=ct,expected=(200,))
    assert task_after["status"]=="matched",task_after

    proposals=call("GET",f"/api/v1/tasks/{task['id']}/proposals",token=ct,expected=(200,)).get("items") or []
    by_id={int(x["id"]):x for x in proposals}
    winning_pid=int(p1["id"] if winner_label=="p1" else p2["id"])
    losing_pid=int(p2["id"] if winner_label=="p1" else p1["id"])
    assert by_id[winning_pid]["status"]=="accepted",by_id
    assert by_id[losing_pid]["status"]=="rejected",by_id

    repeat=raw_call("POST","/api/v1/orders",{"proposal_id":losing_pid},ct)
    assert repeat[0]==409 and repeat[1].get("error")=="order_exists",repeat
    assert int(repeat[1].get("order_id") or 0)==int(winner["id"]),repeat

    return {
        "ok":True,"version":health.get("version"),
        "concurrent_proposal_acceptance":True,
        "single_order_per_task":True,
        "proposal_states_consistent":True,
        "repeat_returns_order_exists":True,
        "task_id":task["id"],"order_id":winner["id"],
        "winning_proposal":winner_label
    }

RESULT=run()
print("MINJAZ_ORDER_CREATION_CONCURRENCY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

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
