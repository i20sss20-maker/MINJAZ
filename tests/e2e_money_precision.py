import json, os, random, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
PORT=int(os.getenv("PORT","3000"))

def call(method,path,body=None,token=None,expected=(200,201)):
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
    payload=json.loads(raw or b"{}")
    assert status in expected,(method,path,status,payload)
    return payload

def login(phone,role,name):
    ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{"challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name})
    return out["token"]

def run():
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    ct=login("+9665"+seed,"client","Money E2E Client")
    ft=login("+9667"+seed,"freelancer","Money E2E Freelancer")

    task=call("POST","/api/v1/tasks",{
      "category_id":cats[0]["id"],"title":"اختبار دقة المبالغ",
      "description":"اختبار آلي للتأكد من تقريب الميزانيات والأسعار والعمولات إلى هللتين بشكل ثابت.",
      "budget_min":"49.995","budget_max":"100.005","urgency":"normal"
    },ct)
    assert abs(float(task["budget_min"])-50.00)<0.0001,task
    assert abs(float(task["budget_max"])-100.01)<0.0001,task

    proposal=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
      "price":"120.115","delivery_hours":24,"revisions":1,"message":"اختبار تقريب مالي."
    },ft)
    assert abs(float(proposal["price"])-120.12)<0.0001,proposal

    order=call("POST","/api/v1/orders",{"proposal_id":proposal["id"]},ct)
    assert abs(float(order["amount"])-120.12)<0.0001,order
    assert abs(float(order["platform_fee"])-18.02)<0.0001,order
    assert abs((float(order["amount"])-float(order["platform_fee"]))-102.10)<0.0001,order

    return {"ok":True,"version":health.get("version"),"budget_rounding":True,"proposal_rounding":True,"fee_rounding":True,"order_id":order["id"]}

RESULT=run()
print("MINJAZ_MONEY_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN","").strip()=="1":
    raise SystemExit(0)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode();self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
