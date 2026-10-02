import json, os, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","http://127.0.0.1:3000").rstrip("/")
ADMIN_PHONE=os.getenv("E2E_ADMIN_PHONE","").strip()
PORT=int(os.getenv("E2E_PORT","3999"))

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

def accept_legal(token):
    out=call("POST","/api/v1/legal/accept",{"documents":["terms","privacy","marketplace_rules"]},token)
    assert out.get("complete") is True,out
    return out

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

def create_completed_order(ct,ft,category_id):
    task=call("POST","/api/v1/tasks",{
        "category_id":category_id,"title":"اختبار اتساق KYC والسحب",
        "description":"اختبار آلي للتأكد من اتساق حالة التحقق مع قرارات السحب المالية ومنع السباقات.",
        "budget_min":"200","budget_max":"240","urgency":"normal"
    },ct)
    proposal=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"200.00","delivery_hours":24,"revisions":1,"message":"عرض اختبار KYC والسحب."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":proposal["id"]},ct)
    call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    call("POST",f"/api/v1/orders/{order['id']}/deliver",{"note":"تسليم اختبار KYC والسحب."},ft)
    call("POST",f"/api/v1/orders/{order['id']}/complete",{},ct)
    return order

def find_payout(at,pid):
    rows=call("GET","/api/admin/payouts",token=at,expected=(200,)).get("items") or []
    return next(x for x in rows if int(x["id"])==int(pid))

def run():
    assert ADMIN_PHONE,"E2E_ADMIN_PHONE is required"
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats

    seed=int(time.time())%90000000+10000000
    client=login(f"+9665{seed:08d}","client","KYC Payout Client")
    freelancer=login(f"+9665{seed+1:08d}","freelancer","KYC Payout Freelancer")
    admin=login(ADMIN_PHONE,"admin","KYC Payout Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]
    fid=freelancer["user"]["id"]
    accept_legal(ct);accept_legal(ft)

    order=create_completed_order(ct,ft,cats[0]["id"])

    approved=call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"approved"},at)
    assert approved["kyc_status"]=="approved",approved

    earnings=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    assert float(earnings.get("available_balance") or 0)>=75,earnings

    payout1=call("POST","/api/v1/freelancer/payouts",{"amount":"50.00","note":"KYC gate test"},ft)["item"]
    pid1=payout1["id"]

    rejected=call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"rejected"},at)
    assert rejected["kyc_status"]=="rejected",rejected

    blocked_processing=raw_call("PATCH",f"/api/admin/payouts/{pid1}",{"status":"processing"},at)
    assert blocked_processing[0]==409 and blocked_processing[1].get("error")=="kyc_required",blocked_processing
    blocked_paid=raw_call("PATCH",f"/api/admin/payouts/{pid1}",{"status":"paid"},at)
    assert blocked_paid[0]==409 and blocked_paid[1].get("error")=="kyc_required",blocked_paid
    assert find_payout(at,pid1)["status"]=="pending"

    call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"approved"},at)
    processing=call("PATCH",f"/api/admin/payouts/{pid1}",{"status":"processing"},at)
    assert processing["item"]["status"]=="processing",processing
    paid=call("PATCH",f"/api/admin/payouts/{pid1}",{"status":"paid"},at)
    assert paid["item"]["status"]=="paid",paid

    # Second payout: race KYC rejection vs final payout decision.
    payout2=call("POST","/api/v1/freelancer/payouts",{"amount":"25.00","note":"KYC race test"},ft)["item"]
    pid2=payout2["id"]
    barrier=Barrier(2)

    def reject_kyc():
        barrier.wait()
        return raw_call("PATCH",f"/api/admin/freelancers/{fid}/kyc",{"status":"rejected"},at)

    def pay_payout():
        barrier.wait()
        return raw_call("PATCH",f"/api/admin/payouts/{pid2}",{"status":"paid"},at)

    with ThreadPoolExecutor(max_workers=2) as ex:
        fk=ex.submit(reject_kyc)
        fp=ex.submit(pay_payout)
        kyc_result=fk.result()
        payout_result=fp.result()

    assert kyc_result[0]==200,kyc_result
    assert payout_result[0] in (200,409),payout_result
    if payout_result[0]==409:
        assert payout_result[1].get("error")=="kyc_required",payout_result

    me=call("GET","/api/v1/me",token=ft,expected=(200,))
    assert me.get("freelancer_profile",{}).get("kyc_status")=="rejected",me
    final2=find_payout(at,pid2)
    assert final2["status"] in ("pending","paid"),final2
    if final2["status"]=="pending":
        again=raw_call("PATCH",f"/api/admin/payouts/{pid2}",{"status":"paid"},at)
        assert again[0]==409 and again[1].get("error")=="kyc_required",again

    final_earnings=call("GET","/api/v1/freelancer/earnings",token=ft,expected=(200,))
    assert float(final_earnings.get("available_balance") or 0)>=0,final_earnings

    return {
        "ok":True,"version":health.get("version"),
        "payout_requires_current_kyc":True,
        "kyc_reapproval_allows_payout":True,
        "kyc_payout_race_deadlock_free":True,
        "non_negative_balance":True,
        "race_payout_status":final2["status"],
        "order_id":order["id"],"payout_ids":[pid1,pid2]
    }

RESULT=run()
print("MINJAZ_KYC_PAYOUT_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)
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
