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
    assert out.get("token") and out["user"]["role"]==role,out
    return out

def run():
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"

    client=login("+9665"+seed,"client","Order Race Client")
    freelancer_a=login("+9667"+seed,"freelancer","Order Race Freelancer A")
    freelancer_b=login("+9668"+seed,"freelancer","Order Race Freelancer B")
    ct=client["token"]; fa=freelancer_a["token"]; fb=freelancer_b["token"]

    task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],
        "title":"اختبار قبول عرضين متزامنين",
        "description":"اختبار آلي للتأكد من أن قبول عرضين مختلفين لنفس المهمة في اللحظة نفسها ينشئ طلباً واحداً فقط.",
        "budget_min":"100","budget_max":"200","urgency":"normal"
    },ct)

    proposal_a=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"120.00","delivery_hours":24,"revisions":2,"message":"العرض الأول لاختبار التزامن."
    },fa)
    proposal_b=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"130.00","delivery_hours":20,"revisions":2,"message":"العرض الثاني لاختبار التزامن."
    },fb)

    barrier=Barrier(2)
    def accept(item):
        label,pid=item
        barrier.wait()
        return label,pid,raw_call("POST","/api/v1/orders",{"proposal_id":pid},ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        results=list(ex.map(accept,[("a",proposal_a["id"]),("b",proposal_b["id"])]))

    statuses=sorted(item[2][0] for item in results)
    assert statuses==[201,409],results

    winning_label,winning_pid,winning_response=next((label,pid,res) for label,pid,res in results if res[0]==201)
    losing_label,losing_pid,losing_response=next((label,pid,res) for label,pid,res in results if res[0]==409)
    order=winning_response[1]
    assert losing_response[1].get("error")=="order_exists",losing_response
    assert int(order["proposal_id"])==int(winning_pid),order

    orders=call("GET","/api/v1/orders",token=ct,expected=(200,)).get("items") or []
    task_orders=[x for x in orders if int(x["task_id"])==int(task["id"])]
    assert len(task_orders)==1,task_orders
    assert int(task_orders[0]["id"])==int(order["id"]),task_orders

    proposals=call("GET",f"/api/v1/tasks/{task['id']}/proposals",token=ct,expected=(200,)).get("items") or []
    by_id={int(x["id"]):x for x in proposals}
    assert by_id[int(winning_pid)]["status"]=="accepted",proposals
    assert by_id[int(losing_pid)]["status"]=="rejected",proposals
    assert sum(1 for x in proposals if x["status"]=="accepted")==1,proposals

    final_task=call("GET",f"/api/v1/tasks/{task['id']}",token=ct,expected=(200,))
    assert final_task["status"]=="matched",final_task

    # Both winner and loser retries should be deterministic conflicts, never 500/404.
    retry_winner=raw_call("POST","/api/v1/orders",{"proposal_id":winning_pid},ct)
    retry_loser=raw_call("POST","/api/v1/orders",{"proposal_id":losing_pid},ct)
    assert retry_winner[0]==409 and retry_winner[1].get("error")=="order_exists",retry_winner
    assert retry_loser[0]==409 and retry_loser[1].get("error")=="order_exists",retry_loser

    paid=call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    assert paid.get("ok") is True and paid.get("mode")=="mock",paid
    active=call("GET",f"/api/v1/orders/{order['id']}",token=ct,expected=(200,))
    assert active["status"]=="in_progress" and active["payment_status"]=="paid",active

    return {
        "ok":True,"version":health.get("version"),
        "single_order":True,
        "single_accepted_proposal":True,
        "loser_conflict":True,
        "repeat_conflict":True,
        "payment_transition":True,
        "winning_proposal":winning_label,
        "order_id":order["id"],
        "task_id":task["id"]
    }

RESULT=run()
print("MINJAZ_ORDER_ACCEPTANCE_CONCURRENCY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
