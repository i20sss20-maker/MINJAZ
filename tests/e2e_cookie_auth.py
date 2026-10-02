import http.cookiejar
import json
import os
import random
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
PORT=int(os.getenv("PORT","3000"))

def request(opener,method,path,body=None,token=None,expected=(200,201)):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode("utf-8")
    headers={"Accept":"application/json"}
    if body is not None:headers["Content-Type"]="application/json"
    if token:headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with opener.open(req,timeout=25) as r:
            status=r.status;raw=r.read()
    except urllib.error.HTTPError as e:
        status=e.code;raw=e.read()
    try:payload=json.loads(raw or b"{}")
    except Exception:payload={"raw":raw.decode(errors="replace")}
    assert status in expected,(method,path,status,payload)
    return payload

def dev_login(opener,phone,name):
    ch=request(opener,"POST","/api/v1/auth/request-otp",{"phone":phone})
    code=ch.get("dev_code")
    assert code,"cookie E2E requires beta/dev OTP"
    out=request(opener,"POST","/api/v1/auth/verify-otp",{
        "challenge_id":ch["challenge_id"],"code":code,"role":"client","name":name
    })
    assert out.get("token"),out
    return out

def cookie_values(jar):
    return [c for c in jar if c.name=="minjaz_session"]

def run():
    health=request(urllib.request.build_opener(),"GET","/health",expected=(200,))
    assert health.get("ok") is True and health.get("database") is True,health

    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"

    # New browser login: verify OTP must establish an HttpOnly secure host cookie.
    jar=http.cookiejar.CookieJar()
    browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login=dev_login(browser,"+9665"+seed,"Cookie E2E Client")
    cookies=cookie_values(jar)
    assert len(cookies)==1,cookies
    cookie=cookies[0]
    assert cookie.path=="/",cookie
    assert cookie.secure is BASE.startswith("https://"),cookie
    rest={str(k).lower():v for k,v in (cookie._rest or {}).items()}
    assert "httponly" in rest,rest
    assert str(rest.get("samesite") or "").lower()=="strict",rest

    me=request(browser,"GET","/api/v1/me",expected=(200,))
    assert me["user"]["name"]=="Cookie E2E Client",me
    sessions=request(browser,"GET","/api/v1/account/sessions",expected=(200,))
    assert any(x.get("current") for x in sessions.get("items") or []),sessions

    request(browser,"POST","/api/v1/auth/logout",{},expected=(200,))
    denied=request(browser,"GET","/api/v1/me",expected=(401,))
    assert denied.get("error")=="unauthorized",denied

    # Legacy localStorage/Bearer migration path: bearer -> session-cookie -> cookie-only.
    legacy_phone="+9668"+seed
    plain=urllib.request.build_opener()
    legacy=dev_login(plain,legacy_phone,"Legacy Upgrade Client")
    legacy_token=legacy["token"]

    jar2=http.cookiejar.CookieJar()
    migrated_browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar2))
    upgraded=request(migrated_browser,"POST","/api/v1/auth/session-cookie",{},legacy_token,expected=(200,))
    assert upgraded.get("ok") is True,upgraded
    assert len(cookie_values(jar2))==1,list(jar2)

    migrated_me=request(migrated_browser,"GET","/api/v1/me",expected=(200,))
    assert migrated_me["user"]["name"]=="Legacy Upgrade Client",migrated_me

    current=next(x for x in request(migrated_browser,"GET","/api/v1/account/sessions",expected=(200,))["items"] if x.get("current"))
    revoked=request(migrated_browser,"DELETE",f"/api/v1/account/sessions/{current['id']}",expected=(200,))
    assert revoked.get("current_revoked") is True,revoked
    denied2=request(migrated_browser,"GET","/api/v1/me",expected=(401,))
    assert denied2.get("error")=="unauthorized",denied2

    return {
        "ok":True,
        "version":health.get("version"),
        "cookie_auth":True,
        "secure":True,
        "httponly":True,
        "samesite_strict":True,
        "logout_revocation":True,
        "legacy_bearer_upgrade":True,
        "current_session_revoke":True
    }

RESULT=run()
print("MINJAZ_COOKIE_AUTH_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN","").strip()=="1":
    raise SystemExit(0)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/health"):
            self.send_response(404);self.end_headers();return
        b=json.dumps(RESULT,ensure_ascii=False).encode()
        self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
