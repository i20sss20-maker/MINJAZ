import http.cookiejar, json, os, random, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","").rstrip("/")
PORT=int(os.getenv("PORT","3000"))
assert BASE,"E2E_BASE_URL is required"

jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def call(method,path,body=None,headers=None,expected=(200,201),use_cookies=True):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    h={"Accept":"application/json",**(headers or {})}
    if body is not None:h["Content-Type"]="application/json"
    req=urllib.request.Request(BASE+path,data=data,headers=h,method=method)
    client=opener if use_cookies else urllib.request.build_opener()
    try:
        with client.open(req,timeout=25) as r:
            status=r.status; raw=r.read(); resp_headers=dict(r.headers.items())
    except urllib.error.HTTPError as e:
        status=e.code; raw=e.read(); resp_headers=dict(e.headers.items())
    try:payload=json.loads(raw or b"{}")
    except Exception:payload={"raw":raw.decode(errors="replace")}
    assert status in expected,(method,path,status,payload)
    return payload,resp_headers

def run():
    health,_=call("GET","/health",expected=(200,))
    assert health.get("ok") is True and health.get("database") is True,health

    phone="+9665"+f"{random.randint(0,99999999):08d}"
    challenge,_=call("POST","/api/v1/auth/request-otp",{"phone":phone})
    assert challenge.get("challenge_id") and challenge.get("dev_code"),challenge

    verified,verify_headers=call("POST","/api/v1/auth/verify-otp",{
        "challenge_id":challenge["challenge_id"],
        "code":challenge["dev_code"],
        "name":"Cookie E2E",
        "role":"client"
    })
    assert verified.get("user",{}).get("phone")==phone,verified
    assert verified.get("session_mode")=="cookie",verified
    assert verified.get("token"),"beta must retain bearer compatibility"

    cookies=list(jar)
    session=[c for c in cookies if c.name=="minjaz_session"]
    assert len(session)==1,cookies
    cookie=session[0]
    assert cookie.value and cookie.path=="/",cookie
    assert cookie.has_nonstandard_attr("HttpOnly"),cookie
    assert str(cookie.get_nonstandard_attr("SameSite") or "").lower()=="lax",cookie

    me,_=call("GET","/api/v1/me",expected=(200,))
    assert me.get("user",{}).get("phone")==phone,me

    sessions,_=call("GET","/api/v1/account/sessions",expected=(200,))
    assert any(x.get("current") for x in sessions.get("items") or []),sessions

    logout,logout_headers=call("POST","/api/v1/auth/logout",{})
    assert logout.get("ok") is True,logout
    assert "max-age=0" in str(logout_headers.get("Set-Cookie","")).lower(),logout_headers

    denied,_=call("GET","/api/v1/me",expected=(401,))
    assert denied.get("error")=="unauthorized",denied

    bearer_denied,_=call("GET","/api/v1/me",headers={"Authorization":"Bearer "+verified["token"]},expected=(401,),use_cookies=False)
    assert bearer_denied.get("error")=="unauthorized",bearer_denied

    return {
        "ok":True,
        "version":health.get("version"),
        "cookie_auth":True,
        "httponly":True,
        "same_site_lax":True,
        "logout_revokes":True,
        "bearer_compatibility":True
    }

RESULT=run()
print("MINJAZ_COOKIE_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
