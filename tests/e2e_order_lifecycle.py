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
    for attempt in range(3):
        status,ch=raw_call("POST","/api/v1/auth/request-otp",{"phone":phone})
        if status==201: break
        if status==429 and attempt<2:
            time.sleep(min(65,int(ch.get("retry_after_seconds") or 60)+1)); continue
        raise AssertionError(("otp_request",status,ch))
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{
        "challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name
    })
    assert out.get("token") and out["user"]["role"]==role,out
    return out

def create_order(ct,ft,cat,title,price="120.00",revisions=2,pay=True):
    task=call("POST","/api/v1/tasks",{
        "category_id":cat,"title":title,
        "description":"اختبار آلي لسلامة انتقالات حالة الطلب عند تنفيذ عمليات متزامنة.",
        "budget_min":"100","budget_max":"180","urgency":"normal"
    },ct)
    prop=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":price,"delivery_hours":24,"revisions":revisions,"message":"عرض اختبار دورة الطلب."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":prop["id"]},ct)
    if pay:
        paid=call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
        assert paid.get("ok") is True and paid.get("mode")=="mock",paid
    return task,order

def concurrent(items):
    barrier=Barrier(len(items))
    def run_one(item):
        label,fn=item
        barrier.wait()
        return label,fn()
    with ThreadPoolExecutor(max_workers=len(items)) as ex:
        return list(ex.map(run_one,items))

def success_count(results):
    return sum(1 for _,(status,_) in results if 200<=status<300)

def run():
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    cat=cats[0]["id"]
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    client=login("+9665"+seed,"client","Lifecycle Client")
    freelancer=login("+9667"+seed,"freelancer","Lifecycle Freelancer")
    ct,ft=client["token"],freelancer["token"]

    # 1) complete vs revision on the same delivered order.
    task1,order1=create_order(ct,ft,cat,"اختبار إكمال ضد تعديل")
    call("POST",f"/api/v1/orders/{order1['id']}/deliver",{"note":"تسليم جاهز للمنافسة."},ft)
    r1=concurrent([
        ("complete",lambda:raw_call("POST",f"/api/v1/orders/{order1['id']}/complete",{},ct)),
        ("revision",lambda:raw_call("POST",f"/api/v1/orders/{order1['id']}/revision",{"note":"طلب تعديل متزامن."},ct))
    ])
    assert success_count(r1)==1 and sum(1 for _,(s,_) in r1 if s==409)==1,r1
    win1=next(label for label,(s,_) in r1 if 200<=s<300)
    o1=call("GET",f"/api/v1/orders/{order1['id']}",token=ct,expected=(200,))
    if win1=="complete":
        assert o1["status"]=="completed",o1
    else:
        assert o1["status"]=="revision_requested",o1

    # 2) complete vs dispute on a delivered order.
    task2,order2=create_order(ct,ft,cat,"اختبار إكمال ضد نزاع")
    call("POST",f"/api/v1/orders/{order2['id']}/deliver",{"note":"تسليم لاختبار الإكمال والنزاع."},ft)
    r2=concurrent([
        ("complete",lambda:raw_call("POST",f"/api/v1/orders/{order2['id']}/complete",{},ct)),
        ("dispute",lambda:raw_call("POST",f"/api/v1/orders/{order2['id']}/dispute",{
            "reason":"نزاع متزامن","details":"اختبار إكمال ونزاع في نفس اللحظة."
        },ft))
    ])
    assert success_count(r2)==1 and sum(1 for _,(s,_) in r2 if s==409)==1,r2
    win2=next(label for label,(s,_) in r2 if 200<=s<300)
    o2=call("GET",f"/api/v1/orders/{order2['id']}",token=ct,expected=(200,))
    assert o2["status"]==("completed" if win2=="complete" else "disputed"),(win2,o2)

    # 3) dispute vs cancellation on an active paid order.
    task3,order3=create_order(ct,ft,cat,"اختبار نزاع ضد إلغاء")
    r3=concurrent([
        ("dispute",lambda:raw_call("POST",f"/api/v1/orders/{order3['id']}/dispute",{
            "reason":"نزاع متزامن","details":"نزاع مقابل إلغاء."
        },ct)),
        ("cancellation",lambda:raw_call("POST",f"/api/v1/orders/{order3['id']}/cancellation",{
            "reason":"إلغاء متزامن","details":"إلغاء مقابل نزاع."
        },ft))
    ])
    assert success_count(r3)==1 and sum(1 for _,(s,_) in r3 if s==409)==1,r3
    win3=next(label for label,(s,_) in r3 if 200<=s<300)
    o3=call("GET",f"/api/v1/orders/{order3['id']}",token=ct,expected=(200,))
    if win3=="dispute":
        assert o3["status"]=="disputed",o3
    else:
        assert o3["status"]=="in_progress",o3
        cancel3=call("GET",f"/api/v1/orders/{order3['id']}/cancellation",token=ct,expected=(200,))["item"]
        assert cancel3["status"]=="pending",cancel3

    # 4) Active cancellation blocks downstream state changes.
    task4,order4=create_order(ct,ft,cat,"اختبار حظر العمليات أثناء الإلغاء")
    call("POST",f"/api/v1/orders/{order4['id']}/cancellation",{
        "reason":"إلغاء قيد المراجعة","details":"يجب حظر التسليم أثناء الطلب المعلق."
    },ct)
    blocked_delivery=raw_call("POST",f"/api/v1/orders/{order4['id']}/deliver",{"note":"يجب أن يرفض."},ft)
    assert blocked_delivery[0]==409 and blocked_delivery[1].get("error")=="active_cancellation_exists",blocked_delivery

    task5,order5=create_order(ct,ft,cat,"اختبار حظر الإكمال أثناء الإلغاء")
    call("POST",f"/api/v1/orders/{order5['id']}/deliver",{"note":"تسليم قبل طلب الإلغاء."},ft)
    call("POST",f"/api/v1/orders/{order5['id']}/cancellation",{
        "reason":"إلغاء بعد التسليم","details":"يجب حظر الإكمال والتعديل."
    },ct)
    blocked_complete=raw_call("POST",f"/api/v1/orders/{order5['id']}/complete",{},ct)
    blocked_revision=raw_call("POST",f"/api/v1/orders/{order5['id']}/revision",{"note":"يجب أن يرفض."},ct)
    assert blocked_complete[0]==409 and blocked_complete[1].get("error")=="active_cancellation_exists",blocked_complete
    assert blocked_revision[0]==409 and blocked_revision[1].get("error")=="active_cancellation_exists",blocked_revision

    # 5) Cancellation before payment blocks payment initialization.
    task6,order6=create_order(ct,ft,cat,"اختبار حظر الدفع أثناء الإلغاء",pay=False)
    call("POST",f"/api/v1/orders/{order6['id']}/cancellation",{
        "reason":"إلغاء قبل الدفع","details":"يجب ألا يبدأ الدفع بعد طلب الإلغاء."
    },ct)
    blocked_pay=raw_call("POST",f"/api/v1/orders/{order6['id']}/pay",{},ct)
    assert blocked_pay[0]==409 and blocked_pay[1].get("error")=="active_cancellation_exists",blocked_pay

    # 6) Unpaid orders cannot open disputes.
    unpaid_dispute=raw_call("POST",f"/api/v1/orders/{order6['id']}/dispute",{
        "reason":"نزاع غير مدفوع","details":"يجب رفض النزاع قبل الدفع."
    },ct)
    assert unpaid_dispute[0]==409 and unpaid_dispute[1].get("error") in ("invalid_order_state","active_cancellation_exists"),unpaid_dispute

    return {
        "ok":True,"version":health.get("version"),
        "complete_vs_revision":True,
        "complete_vs_dispute":True,
        "dispute_vs_cancellation":True,
        "pending_cancellation_blocks_delivery":True,
        "pending_cancellation_blocks_complete":True,
        "pending_cancellation_blocks_revision":True,
        "pending_cancellation_blocks_payment":True,
        "unpaid_dispute_rejected":True,
        "winner_complete_revision":win1,
        "winner_complete_dispute":win2,
        "winner_dispute_cancellation":win3
    }

RESULT=run()
print("MINJAZ_ORDER_LIFECYCLE_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_): pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
# Railway snapshot refresh: order lifecycle E2E
