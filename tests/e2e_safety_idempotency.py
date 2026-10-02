import json, os, random, time, urllib.request, urllib.error

BASE=os.getenv("E2E_BASE_URL","http://127.0.0.1:3000").rstrip("/")

def raw(method,path,body=None,token=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None:headers["Content-Type"]="application/json"
    if token:headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return r.status,json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw_body=e.read()
        try:payload=json.loads(raw_body or b"{}")
        except Exception:payload={"raw":raw_body.decode(errors="replace")}
        return e.code,payload

def call(method,path,body=None,token=None,expected=(200,201)):
    status,payload=raw(method,path,body,token)
    assert status in expected,(path,status,payload)
    return payload

def login(phone,role,name):
    challenge=call("POST","/api/v1/auth/request-otp",{"phone":phone})
    code=challenge.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":challenge["challenge_id"],"code":code,"role":role,"name":name})
    return out

def run():
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    reporter=login("+9665"+seed,"client","Safety Reporter")
    target=login("+9667"+seed,"freelancer","Safety Target")
    token=reporter["token"];target_id=target["user"]["id"]
    key=f"safety-retry-{seed}"
    payload={
        "category":"other",
        "details":"بلاغ ثابت لاختبار منع التكرار عند إعادة المحاولة.",
        "target_user_id":target_id,
        "idempotency_key":key,
    }
    first=raw("POST","/api/v1/safety/reports",payload,token)
    second=raw("POST","/api/v1/safety/reports",payload,token)
    assert first[0]==201,first
    assert second[0]==200,second
    assert int(first[1]["id"])==int(second[1]["id"]),(first,second)
    assert second[1].get("idempotent_replay") is True,second
    items=call("GET","/api/v1/safety/reports",token=token,expected=(200,)).get("items") or []
    matches=[x for x in items if int(x.get("id") or 0)==int(first[1]["id"])]
    assert len(matches)==1,matches
    changed=dict(payload);changed["details"]="بلاغ مختلف بنفس المفتاح لاختبار رفض إعادة الاستخدام."
    conflict=raw("POST","/api/v1/safety/reports",changed,token)
    assert conflict[0]==409 and conflict[1].get("error")=="idempotency_key_reused",conflict
    result={"ok":True,"safety_report_retry_idempotent":True,"single_report_record":True,"key_reuse_rejected":True,"report_id":first[1]["id"]}
    print("MINJAZ_SAFETY_IDEMPOTENCY_E2E_OK",json.dumps(result,ensure_ascii=False),flush=True)

run()
