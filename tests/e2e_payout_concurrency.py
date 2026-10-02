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

def run():
    assert ADMIN_PHONE,"E2E_ADMIN_PHONE is required"
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"

    client=login("+9665"+seed,"client","Payout Race Client")
    freelancer=login("+9667"+seed,"freelancer","Payout Race Freelancer")
    admin=login(ADMIN_PHONE,"admin","Payout Race Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]
    legal={"documents":["terms","privacy","marketplace_rules"]}
    call("POST","/api/v1/legal/accept",legal,ct,expected=(200,))
    call("POST","/api/v1/legal/accept",legal,ft,expected=(200,))
    fid=freelancer["user"]["id"]

    task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سباق السحب المالي",
        "description":"اختبار آلي للتأكد من منع حجز أو صرف الرصيد نفسه مرتين عند الطلبات المتزامنة.",
        "budget_min":"200","budget_max":"250","urgency":"normal"
    },ct)
    proposal=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"200.00","delivery_hours":24,"revisions":1,"message":"عرض لاختبار سباق السحب."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":proposal["id"]},ct)
    call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    call("POST",f"/api/v1/orders/{order['id']}/deliver",{"note":"تسليم اختبار السحب."},ft)
    call("POST",f"/api/v1/orders/{order['id']}/complete",{},ct)
    call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"approved"},at)

    earnings=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    available=round(float(earnings.get("available_balance") or 0),2)
    assert available>0,earnings

    # Two simultaneous requests for the entire available balance: exactly one must reserve it.
    barrier=Barrier(2)
    def create_one(label):
        barrier.wait()
        return raw_call("POST","/api/v1/freelancer/payouts",{
            "amount":f"{available:.2f}","note":f"concurrent-{label}"
        },ft)

    with ThreadPoolExecutor(max_workers=2) as ex:
        results=list(ex.map(create_one,("a","b")))

    statuses=sorted(x[0] for x in results)
    assert statuses==[201,409],results
    winner=next(payload for status,payload in results if status==201)
    loser=next(payload for status,payload in results if status==409)
    assert loser.get("error")=="insufficient_balance",loser
    payout_id=winner["item"]["id"]

    after_reserve=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    assert round(float(after_reserve.get("available_balance") or 0),2)==0.0,after_reserve
    assert round(float(after_reserve.get("pending_payouts") or 0),2)==available,after_reserve

    # Two simultaneous final admin decisions: row lock must allow exactly one final state.
    barrier2=Barrier(2)
    decisions=("paid","rejected")
    def decide(status):
        barrier2.wait()
        return status,raw_call("PATCH",f"/api/admin/payouts/{payout_id}",{
            "status":status,"admin_note":f"concurrent-{status}"
        },at)

    with ThreadPoolExecutor(max_workers=2) as ex:
        decisions_result=list(ex.map(decide,decisions))

    final_statuses=sorted(result[1][0] for result in decisions_result)
    assert final_statuses==[200,409],decisions_result
    winning_decision=next(status for status,(http,payload) in decisions_result if http==200)
    rejected_response=next(payload for status,(http,payload) in decisions_result if http==409)
    assert rejected_response.get("error")=="payout_finalized",rejected_response

    rows=call("GET","/api/admin/payouts",token=at,expected=(200,)).get("items") or []
    row=next(x for x in rows if int(x["id"])==int(payout_id))
    assert row["status"]==winning_decision,(winning_decision,row)

    repeat=raw_call("PATCH",f"/api/admin/payouts/{payout_id}",{
        "status":winning_decision,"admin_note":"repeat-final"
    },at)
    assert repeat[0]==409 and repeat[1].get("error")=="payout_finalized",repeat

    balance=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    assert float(balance.get("available_balance") or 0)>=0,balance
    if winning_decision=="paid":
        assert round(float(balance.get("paid_out") or 0),2)==available,balance
        assert round(float(balance.get("pending_payouts") or 0),2)==0.0,balance
    else:
        assert round(float(balance.get("available_balance") or 0),2)==available,balance
        assert round(float(balance.get("pending_payouts") or 0),2)==0.0,balance

    return {
        "ok":True,"version":health.get("version"),
        "concurrent_balance_reservation":True,
        "concurrent_admin_finality":True,
        "finalized_replay_rejected":True,
        "non_negative_balance":True,
        "winning_admin_decision":winning_decision,
        "payout_id":payout_id,"order_id":order["id"]
    }

RESULT=run()
print("MINJAZ_PAYOUT_CONCURRENCY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

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
