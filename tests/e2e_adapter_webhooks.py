import hashlib,hmac,json,os,random,time,urllib.error,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
PAY_SECRET=os.getenv("E2E_PAYMENT_WEBHOOK_SECRET","").encode()
KYC_SECRET=os.getenv("E2E_KYC_WEBHOOK_SECRET","").encode()
ADMIN_PHONE=os.getenv("E2E_ADMIN_PHONE","").strip()
PORT=int(os.getenv("PORT","3000"))

def call(method,path,body=None,token=None,expected=(200,201),extra_headers=None):
    raw=None if body is None else json.dumps(body,ensure_ascii=False,separators=(",",":")).encode()
    headers={"Accept":"application/json"}
    if raw is not None:headers["Content-Type"]="application/json"
    if token:headers["Authorization"]="Bearer "+token
    if extra_headers:headers.update(extra_headers)
    req=urllib.request.Request(BASE+path,data=raw,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            status=r.status;data=r.read()
    except urllib.error.HTTPError as e:
        status=e.code;data=e.read()
    payload=json.loads(data or b"{}")
    assert status in expected,(method,path,status,payload)
    return payload

def signed(path,payload,secret,expected=(200,)):
    raw=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode()
    sig=hmac.new(secret,raw,hashlib.sha256).hexdigest()
    req=urllib.request.Request(BASE+path,data=raw,headers={"Content-Type":"application/json","Accept":"application/json","X-Minjaz-Signature":sig},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            status=r.status;data=r.read()
    except urllib.error.HTTPError as e:
        status=e.code;data=e.read()
    out=json.loads(data or b"{}")
    assert status in expected,(path,status,out)
    return out

def login(phone,role,name):
    ch=None
    for attempt in range(3):
        ch=call("POST","/api/v1/auth/request-otp",{"phone":phone},expected=(201,429))
        if ch.get("challenge_id"):break
        if ch.get("error") in ("otp_wait","otp_rate_limited","otp_source_rate_limited") and attempt<2:
            time.sleep(min(65,int(ch.get("retry_after_seconds") or 60)+1))
            continue
        raise AssertionError(("otp_request_failed",ch))
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name})
    assert out.get("token"),out
    return out

def run():
    assert len(PAY_SECRET)>=32 and len(KYC_SECRET)>=32 and ADMIN_PHONE,"webhook secrets/admin phone required"
    h=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    client=login("+9665"+seed,"client","Webhook Client")
    freelancer=login("+9667"+seed,"freelancer","Webhook Freelancer")
    admin=login(ADMIN_PHONE,"admin","MINJAZ Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]

    task=call("POST","/api/v1/tasks",{
      "category_id":cats[0]["id"],"title":"اختبار webhook للدفع",
      "description":"اختبار آلي لسلامة توقيع وتكرار وتعارض أحداث مزود الدفع داخل منجاز.",
      "budget_min":"100","budget_max":"180","urgency":"normal"
    },ct)
    prop=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
      "price":"120.12","delivery_hours":24,"revisions":1,"message":"اختبار webhook."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":prop["id"]},ct)
    oid=order["id"]

    payment={
      "event_id":f"pay-{seed}","type":"payment.succeeded",
      "provider_payment_id":f"provider-{seed}","order_id":oid,"amount":"120.12"
    }

    # Bad signature is rejected before processing.
    bad=call("POST","/api/v1/integrations/payments/webhook",payment,expected=(401,),extra_headers={"X-Minjaz-Signature":"0"*64})
    assert bad.get("error")=="invalid_signature",bad

    # Wrong amount is signed but rejected and must not alter order.
    mismatch={**payment,"event_id":f"pay-bad-{seed}","amount":"120.13"}
    mm=signed("/api/v1/integrations/payments/webhook",mismatch,PAY_SECRET,expected=(409,))
    assert mm.get("error")=="amount_mismatch",mm
    before=call("GET",f"/api/v1/orders/{oid}",token=ct,expected=(200,))
    assert before["status"]=="awaiting_payment" and before["payment_status"]=="unpaid",before

    ok=signed("/api/v1/integrations/payments/webhook",payment,PAY_SECRET)
    assert ok.get("ok") is True,ok
    paid=call("GET",f"/api/v1/orders/{oid}",token=ct,expected=(200,))
    assert paid["status"]=="in_progress" and paid["payment_status"]=="paid",paid

    dup=signed("/api/v1/integrations/payments/webhook",payment,PAY_SECRET)
    assert dup.get("duplicate") is True,dup

    conflict={**payment,"type":"payment.failed"}
    cf=signed("/api/v1/integrations/payments/webhook",conflict,PAY_SECRET,expected=(409,))
    assert cf.get("error")=="payment_event_conflict",cf

    late_failure={
      "event_id":f"pay-fail-{seed}","type":"payment.failed",
      "provider_payment_id":payment["provider_payment_id"],"order_id":oid,"amount":"120.12"
    }
    signed("/api/v1/integrations/payments/webhook",late_failure,PAY_SECRET)
    still_paid=call("GET",f"/api/v1/orders/{oid}",token=ct,expected=(200,))
    assert still_paid["status"]=="in_progress" and still_paid["payment_status"]=="paid",still_paid

    # KYC webhook idempotency + conflict immutability.
    uid=freelancer["user"]["id"]
    kyc={"event_id":f"kyc-{seed}","user_id":uid,"status":"approved","provider_reference":f"kyc-ref-{seed}"}
    k1=signed("/api/v1/integrations/kyc/webhook",kyc,KYC_SECRET)
    assert k1.get("ok") is True,k1
    kdup=signed("/api/v1/integrations/kyc/webhook",kyc,KYC_SECRET)
    assert kdup.get("duplicate") is True,kdup
    kconf={**kyc,"provider_reference":f"other-ref-{seed}"}
    kc=signed("/api/v1/integrations/kyc/webhook",kconf,KYC_SECRET,expected=(409,))
    assert kc.get("error")=="kyc_event_conflict",kc

    me=call("GET","/api/v1/me",token=ft,expected=(200,))
    assert me.get("freelancer_profile",{}).get("kyc_status")=="approved",me

    # Payment confirmation after an already-approved cancellation must never reopen work.
    task2=call("POST","/api/v1/tasks",{
      "category_id":cats[0]["id"],"title":"اختبار دفع متأخر بعد الإلغاء",
      "description":"اختبار آلي للتأكد من بقاء الطلب ملغى عند وصول تأكيد دفع متأخر وتحويله للاسترداد اليدوي.",
      "budget_min":"100","budget_max":"180","urgency":"normal"
    },ct)
    prop2=call("POST",f"/api/v1/tasks/{task2['id']}/proposals",{
      "price":"130.00","delivery_hours":24,"revisions":1,"message":"اختبار دفع متأخر."
    },ft)
    order2=call("POST","/api/v1/orders",{"proposal_id":prop2["id"]},ct)
    cancel=call("POST",f"/api/v1/orders/{order2['id']}/cancellation",{
      "reason":"إلغاء اختبار","details":"إلغاء قبل وصول تأكيد الدفع لاختبار المطابقة المالية."
    },ct)
    approved=call("PATCH",f"/api/admin/cancellations/{cancel['id']}",{
      "status":"approved","admin_note":"اعتماد إلغاء قبل وصول الدفع."
    },at)
    assert approved["status"]=="approved" and approved["refund_status"]=="not_needed",approved

    late={
      "event_id":f"pay-late-{seed}","type":"payment.succeeded",
      "provider_payment_id":f"provider-late-{seed}","order_id":order2["id"],"amount":"130.00"
    }
    signed("/api/v1/integrations/payments/webhook",late,PAY_SECRET)
    late_order=call("GET",f"/api/v1/orders/{order2['id']}",token=ct,expected=(200,))
    assert late_order["status"]=="cancelled" and late_order["payment_status"]=="paid",late_order
    late_cancel=call("GET",f"/api/v1/orders/{order2['id']}/cancellation",token=ct,expected=(200,))["item"]
    assert late_cancel["refund_status"]=="manual_required",late_cancel

    reconciled=call("PATCH",f"/api/admin/cancellations/{cancel['id']}",{
      "refund_status":"refunded","admin_note":"تمت مطابقة الاسترداد بعد الدفع المتأخر."
    },at)
    assert reconciled["refund_status"]=="refunded",reconciled
    refunded_order=call("GET",f"/api/v1/orders/{order2['id']}",token=ct,expected=(200,))
    assert refunded_order["status"]=="cancelled" and refunded_order["payment_status"]=="refunded",refunded_order

    return {"ok":True,"version":h.get("version"),"payment_signature":True,"amount_mismatch":True,"payment_idempotency":True,"payment_conflict":True,"late_failure_safe":True,"kyc_idempotency":True,"kyc_conflict":True,"late_cancelled_payment_safe":True,"manual_refund_reconciliation":True,"order_id":oid,"late_order_id":order2["id"]}

RESULT=run()
print("MINJAZ_ADAPTER_WEBHOOK_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode();self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
