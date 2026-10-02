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

def run():
    assert ADMIN_PHONE,"E2E_ADMIN_PHONE is required"
    health=call("GET","/health",expected=(200,))
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    client=login("+9665"+seed,"client","Privacy Race Client")
    admin=login(ADMIN_PHONE,"admin","Privacy Race Admin")
    ct,at=client["token"],admin["token"]

    req=call("POST","/api/v1/privacy/requests",{
        "request_type":"access",
        "details":"اختبار آلي للتأكد من أن طلب الخصوصية لا يمكن إنهاؤه بحالتين نهائيتين متعارضتين في نفس اللحظة."
    },ct)

    barrier=Barrier(2)
    payloads=[
        ("completed",{"status":"completed","admin_note":"إنهاء متزامن completed"}),
        ("rejected",{"status":"rejected","admin_note":"إنهاء متزامن rejected"})
    ]
    def decide(item):
        label,body=item
        barrier.wait()
        return label,raw_call("PATCH",f"/api/admin/privacy/{req['id']}",body,at)

    with ThreadPoolExecutor(max_workers=2) as ex:
        results=list(ex.map(decide,payloads))

    assert sorted(x[1][0] for x in results)==[200,409],results
    winner=next(label for label,(http,payload) in results if http==200)
    loser=next(payload for label,(http,payload) in results if http==409)
    assert loser.get("error")=="privacy_request_finalized",loser

    rows=call("GET","/api/admin/privacy",token=at,expected=(200,)).get("items") or []
    row=next(x for x in rows if int(x["id"])==int(req["id"]))
    assert row["status"]==winner,row
    assert row.get("resolved_at"),row

    opposite="rejected" if winner=="completed" else "completed"
    repeat=raw_call("PATCH",f"/api/admin/privacy/{req['id']}",{
        "status":opposite,"admin_note":"محاولة تغيير القرار النهائي"
    },at)
    assert repeat[0]==409 and repeat[1].get("error")=="privacy_request_finalized",repeat

    reopen=raw_call("PATCH",f"/api/admin/privacy/{req['id']}",{
        "status":"in_progress","admin_note":"محاولة إعادة فتح قرار نهائي"
    },at)
    assert reopen[0]==409 and reopen[1].get("error")=="privacy_request_finalized",reopen

    return {
        "ok":True,"version":health.get("version"),
        "privacy_concurrency":True,
        "privacy_finality":True,
        "resolved_at_preserved":True,
        "winning_status":winner,
        "privacy_request_id":req["id"]
    }

RESULT=run()
print("MINJAZ_PRIVACY_CONCURRENCY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN","").strip()=="1":
    raise SystemExit(0)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_): pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
