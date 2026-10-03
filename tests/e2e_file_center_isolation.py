import json, os, random, time, urllib.request, urllib.error

BASE=os.getenv("E2E_BASE_URL","https://minjaz-ops-integrity-target-production.up.railway.app").rstrip("/")
PORT=int(os.getenv("PORT","3000"))

def call(method,path,body=None,token=None,expected=(200,201)):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            payload=json.loads(r.read() or b"{}")
            assert r.status in expected,(path,r.status,payload)
            return payload
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: payload=json.loads(raw or b"{}")
        except Exception: payload={"raw":raw.decode(errors="replace")}
        raise AssertionError((path,e.code,payload)) from e

def login(phone,role,name):
    ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name})
    assert out.get("token"),out
    return out

def create_order(ct,ft,category_id,title):
    task=call("POST","/api/v1/tasks",{
        "category_id":category_id,
        "title":title,
        "description":"اختبار آلي مستقل للتحقق من عزل مركز الملفات بين حسابات مِنجاز.",
        "budget_min":100,"budget_max":160,"urgency":"normal"
    },ct)
    proposal=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":120,"delivery_hours":24,"revisions":2,"message":"عرض اختبار عزل الملفات."
    },ft)
    order=call("POST","/api/v1/orders",{"proposal_id":proposal["id"]},ct)
    paid=call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)
    assert paid.get("ok") is True,paid
    return task,order

def run():
    health=call("GET","/health",expected=(200,))
    assert health.get("ok") is True and health.get("database") is True,health
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats,"categories_empty"

    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    outsider_seed=f"{(int(seed)+137)%100000000:08d}"
    client=login("+9665"+seed,"client","Files E2E Client")
    freelancer=login("+9667"+seed,"freelancer","Files E2E Freelancer")
    outsider=login("+9665"+outsider_seed,"client","Files E2E Outsider")
    ct,ft,ot=client["token"],freelancer["token"],outsider["token"]

    docs={"documents":["terms","privacy","marketplace_rules"]}
    for token in (ct,ft,ot):
        assert call("POST","/api/v1/legal/accept",docs,token,expected=(200,)).get("complete") is True

    task,order=create_order(ct,ft,cats[0]["id"],"اختبار عزل مركز الملفات")
    file_name=f"scope-{seed}.txt"
    msg=call("POST",f"/api/v1/orders/{order['id']}/messages",{
        "body":"ملف خاص بطرفي الطلب فقط.",
        "attachments":[{
            "file_name":file_name,
            "file_url":BASE+"/icon.svg",
            "mime_type":"text/plain",
            "size_bytes":31
        }]
    },ct,expected=(201,))
    assert msg.get("attachments"),msg

    client_files=call("GET","/api/v1/files",token=ct,expected=(200,)).get("items") or []
    freelancer_files=call("GET","/api/v1/files",token=ft,expected=(200,)).get("items") or []
    outsider_files=call("GET","/api/v1/files",token=ot,expected=(200,)).get("items") or []

    assert any(x.get("file_name")==file_name and int(x.get("order_id") or 0)==int(order["id"]) for x in client_files),client_files
    assert any(x.get("file_name")==file_name and int(x.get("order_id") or 0)==int(order["id"]) for x in freelancer_files),freelancer_files
    assert not any(x.get("file_name")==file_name for x in outsider_files),outsider_files

    return {
        "ok":True,
        "version":health.get("version"),
        "release_commit":health.get("release_commit"),
        "file_center_isolation":True,
        "order_id":order["id"],
        "task_id":task["id"]
    }

RESULT=run()
print("MINJAZ_FILE_CENTER_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN","1")=="1":
    raise SystemExit(0)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers();self.wfile.write(b)
    def log_message(self,*_): pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
