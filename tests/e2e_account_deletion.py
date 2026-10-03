import json, os, random, time, urllib.error, urllib.request

BASE=os.getenv("E2E_BASE_URL","http://127.0.0.1:3000").rstrip("/")
ADMIN_PHONE=os.getenv("E2E_ADMIN_PHONE","+966599999995")

def call(method,path,body=None,token=None,expected=(200,201)):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    headers={"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            status=r.status; raw=r.read()
    except urllib.error.HTTPError as e:
        status=e.code; raw=e.read()
    payload=json.loads(raw or b"{}")
    assert status in expected,(method,path,status,payload)
    return payload

def login(phone,name,role="client"):
    ch=call("POST","/api/v1/auth/request-otp",{"phone":phone})
    assert ch.get("dev_code"),ch
    return call("POST","/api/v1/auth/verify-otp",{
        "challenge_id":ch["challenge_id"],"code":ch["dev_code"],"role":role,"name":name
    })

def run():
    seed=f"{int(time.time())%1000000:06d}{random.randint(10,99)}"
    phone="+96657"+seed[-7:]
    user=login(phone,"Deletion E2E User")
    token=user["token"]; uid=int(user["user"]["id"])
    call("POST","/api/v1/support/tickets",{
        "subject":"Deletion private subject","message":"Deletion private message",
        "idempotency_key":"support-delete-"+seed
    },token)
    req=call("POST","/api/v1/privacy/requests",{
        "request_type":"delete","details":"Delete this test account",
        "idempotency_key":"privacy-delete-"+seed
    },token)
    admin=login(ADMIN_PHONE,"Deletion E2E Admin")
    assert admin["user"]["role"]=="admin",admin
    done=call("PATCH",f"/api/admin/privacy/{int(req['id'])}",{
        "status":"completed","admin_note":"Deletion E2E execution"
    },admin["token"])
    assert done.get("account_deleted") is True and done.get("deletion_executed_at"),done
    denied=call("GET","/api/v1/me",token=token,expected=(401,))
    assert denied.get("error")=="unauthorized",denied
    users=call("GET","/api/admin/users",token=admin["token"]).get("items") or []
    row=next(x for x in users if int(x["id"])==uid)
    assert row["name"]=="مستخدم محذوف" and row["phone"]!=phone and row.get("deleted_at"),row
    fresh=login(phone,"Fresh Recreated User")
    assert int(fresh["user"]["id"])!=uid,(uid,fresh)
    return {"ok":True,"account_deletion":True,"session_revoked":True,"identity_anonymized":True,
            "phone_released":True,"deleted_user_id":uid,"recreated_user_id":int(fresh["user"]["id"])}

print("MINJAZ_ACCOUNT_DELETION_E2E_OK",json.dumps(run(),ensure_ascii=False),flush=True)
