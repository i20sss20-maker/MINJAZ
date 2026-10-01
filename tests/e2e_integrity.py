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
            status=r.status; raw=r.read()
    except urllib.error.HTTPError as e:
        status=e.code; raw=e.read()
    try: payload=json.loads(raw or b"{}")
    except Exception: payload={"raw":raw.decode(errors="replace")}
    assert status in expected,(method,path,status,payload)
    return payload

def login(phone,role,name):
    for attempt in range(3):
        try:
            ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
            break
        except AssertionError as exc:
            info=exc.args[0] if exc.args else ()
            if attempt<2 and isinstance(info,tuple) and len(info)>=4 and info[2]==429:
                delay=min(65,int((info[3] or {}).get("retry_after_seconds") or 60)+1)
                time.sleep(delay);continue
            raise
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name})
    assert out.get("token") and out["user"]["role"]==role,out
    return out

def create_task(ct,cat,title):
    return call("POST","/api/v1/tasks",{
        "category_id":cat,"title":title,
        "description":"اختبار نزاهة آلي لمنصة منجاز للتحقق من الحالات الحساسة ومنع الانتقالات غير الصحيحة.",
        "budget_min":100,"budget_max":180,"urgency":"normal"
    },ct)

def create_paid_order(ct,ft,cat,title):
    task=create_task(ct,cat,title)
    prop=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":120,"delivery_hours":24,"revisions":2,"message":"عرض اختبار نزاهة."
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
    client=login("+9665"+seed,"client","Integrity Client")
    freelancer=login("+9667"+seed,"freelancer","Integrity Freelancer")
    admin=login(ADMIN_PHONE,"admin","MINJAZ Admin")
    ct,ft,at=client["token"],freelancer["token"],admin["token"]
    cid,fid=client["user"]["id"],freelancer["user"]["id"]

    # Blocking lifecycle.
    call("POST",f"/api/v1/blocks/{fid}",{"reason":"اختبار الحظر"},ct)
    blocks=call("GET","/api/v1/blocks",token=ct,expected=(200,)).get("items") or []
    assert any(int(x["user_id"])==int(fid) for x in blocks),blocks
    call("DELETE",f"/api/v1/blocks/{fid}",token=ct,expected=(200,))

    # Safety moderation must actively prevent new interactions, then recover after unrestrict.
    safety_task=create_task(ct,cat,"اختبار تقييد الأمان")
    report=call("POST","/api/v1/safety/reports",{
        "category":"other","details":"بلاغ اختبار نزاهة لمسار تقييد التعاملات وإعادة فتحها بعد المراجعة.",
        "target_user_id":fid
    },ct)
    call("PATCH",f"/api/admin/safety/reports/{report['id']}",{
        "status":"resolved","user_action":"restrict","admin_note":"تقييد اختبار مؤقت."
    },at)
    denied=call("POST",f"/api/v1/tasks/{safety_task['id']}/proposals",{
        "price":120,"delivery_hours":24,"revisions":1,"message":"يجب رفض هذا العرض أثناء التقييد."
    },ft,expected=(403,))
    assert denied.get("error")=="interaction_restricted",denied
    call("PATCH",f"/api/admin/safety/reports/{report['id']}",{
        "status":"resolved","user_action":"unrestrict","admin_note":"رفع تقييد الاختبار."
    },at)
    accepted=call("POST",f"/api/v1/tasks/{safety_task['id']}/proposals",{
        "price":120,"delivery_hours":24,"revisions":1,"message":"عرض بعد رفع التقييد."
    },ft)
    assert accepted.get("id"),accepted

    # Dispute cancellation must refund mock payment and become immutable.
    _,order=create_paid_order(ct,ft,cat,"اختبار إلغاء نزاع واسترداد")
    dispute=call("POST",f"/api/v1/orders/{order['id']}/dispute",{
        "reason":"نزاع نزاهة","details":"يجب أن يؤدي قرار الإلغاء إلى استرداد دفع mock وإقفال النزاع."
    },ct)
    resolved=call("PATCH",f"/api/admin/disputes/{dispute['id']}",{
        "status":"resolved","action":"cancel","resolution_note":"إلغاء اختبار مع استرداد."
    },at)
    assert resolved["status"]=="resolved" and resolved.get("refund_status")=="refunded",resolved
    final_order=call("GET",f"/api/v1/orders/{order['id']}",token=ct,expected=(200,))
    assert final_order["status"]=="cancelled" and final_order["payment_status"]=="refunded",final_order
    again=call("PATCH",f"/api/admin/disputes/{dispute['id']}",{
        "status":"resolved","action":"resume","resolution_note":"يجب رفض إعادة فتح نزاع محسوم."
    },at,expected=(409,))
    assert again.get("error")=="dispute_finalized",again

    # Support workflow rejects arbitrary states and unknown IDs.
    ticket=call("POST","/api/v1/support/tickets",{
        "category":"technical","subject":"اختبار نزاهة الدعم","message":"التحقق من الحالات المسموحة فقط.","priority":"normal"
    },ct)
    bad_support=call("PATCH",f"/api/admin/support/{ticket['id']}",{"status":"banana"},at,expected=(400,))
    assert bad_support.get("error")=="invalid_status",bad_support
    call("PATCH",f"/api/admin/support/{ticket['id']}",{"status":"resolved","admin_reply":"تم الحل."},at)
    missing_support=call("PATCH","/api/admin/support/2147483647",{"status":"resolved"},at,expected=(404,))
    assert missing_support.get("error")=="support_ticket_not_found",missing_support

    # Privacy requests are final once completed/rejected.
    privacy=call("POST","/api/v1/privacy/requests",{
        "request_type":"access","details":"اختبار نزاهة دورة طلب الخصوصية."
    },ct)
    bad_privacy=call("PATCH",f"/api/admin/privacy/{privacy['id']}",{"status":"banana"},at,expected=(400,))
    assert bad_privacy.get("error")=="invalid_status",bad_privacy
    done=call("PATCH",f"/api/admin/privacy/{privacy['id']}",{"status":"completed","admin_note":"اكتمل الاختبار."},at)
    assert done["status"]=="completed" and done.get("resolved_at"),done
    reopen=call("PATCH",f"/api/admin/privacy/{privacy['id']}",{"status":"in_progress"},at,expected=(409,))
    assert reopen.get("error")=="privacy_request_finalized",reopen
    missing_privacy=call("PATCH","/api/admin/privacy/2147483647",{"status":"completed"},at,expected=(404,))
    assert missing_privacy.get("error")=="privacy_request_not_found",missing_privacy

    # Manual KYC endpoint validates target existence in beta/manual mode.
    missing_kyc=call("PATCH","/api/admin/freelancers/2147483647/kyc",{"status":"approved"},at,expected=(404,))
    assert missing_kyc.get("error")=="freelancer_not_found",missing_kyc

    # Current-session revocation must invalidate the token immediately after the revoke response.
    sessions=call("GET","/api/v1/account/sessions",token=ct,expected=(200,)).get("items") or []
    current=next(x for x in sessions if x.get("current"))
    revoked=call("DELETE",f"/api/v1/account/sessions/{current['id']}",token=ct,expected=(200,))
    assert revoked.get("current_revoked") is True,revoked
    unauthorized=call("GET","/api/v1/me",token=ct,expected=(401,))
    assert unauthorized.get("error")=="unauthorized",unauthorized

    return {
        "ok":True,"version":health.get("version"),
        "blocks":True,"safety_restrict_unrestrict":True,
        "dispute_cancel_refund":True,"dispute_finality":True,
        "support_state_validation":True,"privacy_finality":True,
        "kyc_target_validation":True,"session_revocation":True,
        "dispute_order_id":order["id"],"report_id":report["id"]
    }

RESULT=run()
print("MINJAZ_INTEGRITY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_): pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
