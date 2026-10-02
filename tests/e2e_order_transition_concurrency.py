import json, os, random, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
PORT=int(os.getenv("PORT","3000"))
ADMIN_PHONE=os.getenv("ADMIN_PHONE","+966599999995")

def raw_call(method,path,body=None,token=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            status=r.status;raw=r.read()
    except urllib.error.HTTPError as e:
        status=e.code;raw=e.read()
    try: payload=json.loads(raw or b"{}")
    except Exception: payload={"raw":raw.decode(errors="replace")}
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
    ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{
        "challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name
    })
    assert out.get("token"),out
    return out

def create_paid_order(ct,ft,cat,title,revisions=2,price="140.00"):
    task=call("POST","/api/v1/tasks",{
        "category_id":cat,"title":title,
        "description":"اختبار آلي لتزامن انتقالات الطلب ومنع الكتابة فوق حالات النزاع والإلغاء والإكمال.",
        "budget_min":"100","budget_max":"220","urgency":"normal"
    },ct)
    proposal=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":price,"delivery_hours":24,"revisions":revisions,"message":"عرض اختبار انتقالات متزامنة."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":proposal["id"]},ct)
    paid=call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    assert paid.get("ok") is True and paid.get("mode")=="mock",paid
    return task,order

def concurrent(calls):
    barrier=Barrier(len(calls))
    def runner(item):
        label,method,path,body,token=item
        barrier.wait()
        return label,raw_call(method,path,body,token)
    with ThreadPoolExecutor(max_workers=len(calls)) as ex:
        return list(ex.map(runner,calls))

def run():
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    cat=cats[0]["id"]
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    client=login("+9665"+seed,"client","Transition Race Client")
    freelancer=login("+9667"+seed,"freelancer","Transition Race Freelancer")
    admin=login(ADMIN_PHONE,"admin","Transition Race Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]
    accept_legal(ct);accept_legal(ft)

    # Two cancellation requests at the same instant: exactly one active case.
    _,o1=create_paid_order(ct,ft,cat,"اختبار إلغاء مزدوج")
    c1=concurrent([
        ("client","POST",f"/api/v1/orders/{o1['id']}/cancellation",{"reason":"إلغاء عميل","details":"طلب متزامن من العميل"},ct),
        ("freelancer","POST",f"/api/v1/orders/{o1['id']}/cancellation",{"reason":"إلغاء مستقل","details":"طلب متزامن من المستقل"},ft),
    ])
    assert sorted(x[1][0] for x in c1)==[201,409],c1
    loser=next(payload for _,(status,payload) in c1 if status==409)
    assert loser.get("error")=="active_cancellation_exists",loser

    cxl_item=call("GET",f"/api/v1/orders/{o1['id']}/cancellation",token=ct,expected=(200,)).get("item")
    assert cxl_item and cxl_item.get("id"),cxl_item
    cxl_id=int(cxl_item["id"])
    review_body={"status":"in_review","admin_note":"مراجعة إدارية ثابتة"}
    review1=call("PATCH",f"/api/admin/cancellations/{cxl_id}",review_body,at)
    review2=call("PATCH",f"/api/admin/cancellations/{cxl_id}",review_body,at)
    assert review1.get("status")=="in_review" and not review1.get("idempotent_replay"),review1
    assert review2.get("idempotent_replay") is True,review2
    cb=call("GET","/api/v1/notifications?kind=cancellation&limit=100",token=ct,expected=(200,)).get("items") or []
    fb=call("GET","/api/v1/notifications?kind=cancellation&limit=100",token=ft,expected=(200,)).get("items") or []
    reject_body={"status":"rejected","admin_note":"رفض إداري ثابت"}
    reject1=call("PATCH",f"/api/admin/cancellations/{cxl_id}",reject_body,at)
    reject2=call("PATCH",f"/api/admin/cancellations/{cxl_id}",reject_body,at)
    assert reject1.get("status")=="rejected" and not reject1.get("idempotent_replay"),reject1
    assert reject2.get("idempotent_replay") is True,reject2
    ca=call("GET","/api/v1/notifications?kind=cancellation&limit=100",token=ct,expected=(200,)).get("items") or []
    fa=call("GET","/api/v1/notifications?kind=cancellation&limit=100",token=ft,expected=(200,)).get("items") or []
    assert len(ca)==len(cb)+1,(cb,ca)
    assert len(fa)==len(fb)+1,(fb,fa)

    # Two dispute opens at the same instant: exactly one active dispute.
    _,o2=create_paid_order(ct,ft,cat,"اختبار نزاع مزدوج")
    d1=concurrent([
        ("client","POST",f"/api/v1/orders/{o2['id']}/dispute",{"reason":"نزاع عميل","details":"نزاع متزامن من العميل"},ct),
        ("freelancer","POST",f"/api/v1/orders/{o2['id']}/dispute",{"reason":"نزاع مستقل","details":"نزاع متزامن من المستقل"},ft),
    ])
    assert sorted(x[1][0] for x in d1)==[201,409],d1
    loser=next(payload for _,(status,payload) in d1 if status==409)
    assert loser.get("error")=="active_dispute_exists",loser
    final_o2=call("GET",f"/api/v1/orders/{o2['id']}",token=ct,expected=(200,))
    assert final_o2["status"]=="disputed",final_o2

    dispute_item=call("GET",f"/api/v1/orders/{o2['id']}/dispute",token=ct,expected=(200,)).get("item")
    assert dispute_item and dispute_item.get("id"),dispute_item
    did=int(dispute_item["id"])
    review_body={"status":"in_review","resolution_note":"stable dispute review"}
    review1=call("PATCH",f"/api/admin/disputes/{did}",review_body,at)
    review2=call("PATCH",f"/api/admin/disputes/{did}",review_body,at)
    assert review1.get("status")=="in_review" and not review1.get("idempotent_replay"),review1
    assert review2.get("idempotent_replay") is True,review2
    resolve_body={"status":"resolved","action":"resume","resolution_note":"stable dispute resolution"}
    resolve1=call("PATCH",f"/api/admin/disputes/{did}",resolve_body,at)
    resolve2=call("PATCH",f"/api/admin/disputes/{did}",resolve_body,at)
    assert resolve1.get("status")=="resolved" and not resolve1.get("idempotent_replay"),resolve1
    assert resolve2.get("idempotent_replay") is True,resolve2

    # Retrying the same cancellation request with one key returns the same case and notifies once.
    _,oc=create_paid_order(ct,ft,cat,"اختبار إعادة طلب الإلغاء")
    cancel_key=f"cancel-race-{seed}"
    cancel_payload={"reason":"إلغاء ثابت","details":"إعادة المحاولة بنفس المفتاح","idempotency_key":cancel_key}
    cancel_retry=concurrent([
        ("first","POST",f"/api/v1/orders/{oc['id']}/cancellation",cancel_payload,ct),
        ("retry","POST",f"/api/v1/orders/{oc['id']}/cancellation",cancel_payload,ct),
    ])
    assert sorted(x[1][0] for x in cancel_retry)==[200,201],cancel_retry
    cancel_ids={int(payload["id"]) for _,(_,payload) in cancel_retry}
    assert len(cancel_ids)==1,cancel_retry
    assert sum(1 for _,(_,payload) in cancel_retry if payload.get("idempotent_replay"))==1,cancel_retry
    cancel_notes=call("GET","/api/v1/notifications?kind=cancellation&limit=50",token=ft,expected=(200,)).get("items") or []
    cancel_notes=[x for x in cancel_notes if int(x.get("order_id") or 0)==int(oc["id"])]
    assert len(cancel_notes)==1,cancel_notes

    # Retrying the same dispute with one key returns the same dispute and notifies once.
    _,od=create_paid_order(ct,ft,cat,"اختبار إعادة فتح النزاع")
    dispute_key=f"dispute-race-{seed}"
    dispute_payload={"reason":"نزاع ثابت","details":"إعادة المحاولة بنفس المفتاح","idempotency_key":dispute_key}
    dispute_retry=concurrent([
        ("first","POST",f"/api/v1/orders/{od['id']}/dispute",dispute_payload,ct),
        ("retry","POST",f"/api/v1/orders/{od['id']}/dispute",dispute_payload,ct),
    ])
    assert sorted(x[1][0] for x in dispute_retry)==[200,201],dispute_retry
    dispute_ids={int(payload["id"]) for _,(_,payload) in dispute_retry}
    assert len(dispute_ids)==1,dispute_retry
    assert sum(1 for _,(_,payload) in dispute_retry if payload.get("idempotent_replay"))==1,dispute_retry
    dispute_notes=call("GET","/api/v1/notifications?kind=dispute&limit=50",token=ft,expected=(200,)).get("items") or []
    dispute_notes=[x for x in dispute_notes if int(x.get("order_id") or 0)==int(od["id"])]
    assert len(dispute_notes)==1,dispute_notes

    # Completion and cancellation creation racing on a delivered order: one wins, never both.
    _,o3=create_paid_order(ct,ft,cat,"اختبار إكمال مقابل إلغاء")
    call("POST",f"/api/v1/orders/{o3['id']}/deliver",{"note":"تسليم قبل سباق الإكمال والإلغاء."},ft)
    r3=concurrent([
        ("complete","POST",f"/api/v1/orders/{o3['id']}/complete",{},ct),
        ("cancel","POST",f"/api/v1/orders/{o3['id']}/cancellation",{"reason":"إلغاء أثناء الإكمال","details":"سباق مالي نهائي"},ct),
    ])
    assert sorted(x[1][0] for x in r3)==[200,409] or sorted(x[1][0] for x in r3)==[201,409],r3
    winner=next(label for label,(status,_) in r3 if status in (200,201))
    final_o3=call("GET",f"/api/v1/orders/{o3['id']}",token=ct,expected=(200,))
    if winner=="complete":
        assert final_o3["status"]=="completed",final_o3
        cancel_state=call("GET",f"/api/v1/orders/{o3['id']}/cancellation",token=ct,expected=(200,))
        assert cancel_state.get("item") is None,cancel_state
    else:
        assert final_o3["status"]=="delivered",final_o3
        second_complete=raw_call("POST",f"/api/v1/orders/{o3['id']}/complete",{},ct)
        assert second_complete[0]==409 and second_complete[1].get("error")=="active_cancellation_exists",second_complete

    # Delivery and dispute can race, but dispute must dominate final workflow state.
    _,o4=create_paid_order(ct,ft,cat,"اختبار تسليم مقابل نزاع")
    r4=concurrent([
        ("deliver","POST",f"/api/v1/orders/{o4['id']}/deliver",{"note":"تسليم متزامن مع نزاع."},ft),
        ("dispute","POST",f"/api/v1/orders/{o4['id']}/dispute",{"reason":"نزاع أثناء التسليم","details":"يجب أن تكون الحالة النهائية نزاعًا"},ct),
    ])
    dispute_result=next((x for x in r4 if x[0]=="dispute"),None)
    assert dispute_result and dispute_result[1][0]==201,r4
    deliver_status=next(x[1][0] for x in r4 if x[0]=="deliver")
    assert deliver_status in (201,409),r4
    final_o4=call("GET",f"/api/v1/orders/{o4['id']}",token=ct,expected=(200,))
    assert final_o4["status"]=="disputed",final_o4
    deliveries=call("GET",f"/api/v1/orders/{o4['id']}/deliveries",token=ct,expected=(200,)).get("items") or []
    if deliver_status==201:
        assert len(deliveries)>=1,deliveries

    # Revision vs dispute: if revision lands first it may be recorded, but dispute remains the final state.
    _,o5=create_paid_order(ct,ft,cat,"اختبار تعديل مقابل نزاع",revisions=2)
    call("POST",f"/api/v1/orders/{o5['id']}/deliver",{"note":"تسليم قبل سباق التعديل والنزاع."},ft)
    r5=concurrent([
        ("revision","POST",f"/api/v1/orders/{o5['id']}/revision",{"note":"تعديل متزامن مع النزاع"},ct),
        ("dispute","POST",f"/api/v1/orders/{o5['id']}/dispute",{"reason":"نزاع أثناء التعديل","details":"النزاع يجب أن يهيمن على الحالة النهائية"},ft),
    ])
    d5=next(x for x in r5 if x[0]=="dispute")
    assert d5[1][0]==201,r5
    rev_status=next(x[1][0] for x in r5 if x[0]=="revision")
    assert rev_status in (200,409),r5
    final_o5=call("GET",f"/api/v1/orders/{o5['id']}",token=ct,expected=(200,))
    assert final_o5["status"]=="disputed",final_o5

    return {
        "ok":True,"version":health.get("version"),
        "double_cancellation_serialized":True,
        "double_dispute_serialized":True,
        "cancellation_retry_idempotent":True,
        "dispute_retry_idempotent":True,
        "single_case_notifications":True,
        "complete_vs_cancellation_safe":True,
        "deliver_vs_dispute_safe":True,
        "revision_vs_dispute_safe":True,
        "orders":[o1["id"],o2["id"],o3["id"],o4["id"],o5["id"]]
    }

RESULT=run()
print("MINJAZ_ORDER_TRANSITION_CONCURRENCY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

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
