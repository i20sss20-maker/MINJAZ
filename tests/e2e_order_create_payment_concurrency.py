import json, os, random, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=os.getenv("E2E_BASE_URL","https://minjaz-stage-fixed-production.up.railway.app").rstrip("/")
PORT=int(os.getenv("PORT","3000"))

def raw_call(method,path,body=None,token=None):
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
    try:payload=json.loads(raw or b"{}")
    except Exception:payload={"raw":raw.decode(errors="replace")}
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
    for attempt in range(3):
        status,ch=raw_call("POST","/api/v1/auth/request-otp",{"phone":phone})
        if status==201:break
        if status==429 and attempt<2:
            time.sleep(min(65,int(ch.get("retry_after_seconds") or 60)+1));continue
        raise AssertionError(("otp_request",status,ch))
    code=ch.get("dev_code") or "1234"
    out=call("POST","/api/v1/auth/verify-otp",{
        "challenge_id":ch["challenge_id"],"code":code,"role":role,"name":name
    })
    assert out.get("token"),out
    return out

def run():
    health=call("GET","/health",expected=(200,))
    cats=call("GET","/api/v1/categories",expected=(200,)).get("items") or []
    assert cats
    base=int(time.time())%90000000+10000000
    phones=[f"+9665{base+i:08d}" for i in range(3)]

    client=login(phones[0],"client","Order Race Client")
    f1=login(phones[1],"freelancer","Order Race Freelancer A")
    f2=login(phones[2],"freelancer","Order Race Freelancer B")
    ct,t1,t2=client["token"],f1["token"],f2["token"]
    accept_legal(ct);accept_legal(t1);accept_legal(t2)

    search_key=f"saved-search-race-{base}"
    search_payload={"name":"Saved search retry","filters":{"urgency":"urgent","sort":"latest","min_budget":"100"},"idempotency_key":search_key}
    search_barrier=Barrier(2)
    def save_same_search():
        search_barrier.wait()
        return raw_call("POST","/api/v1/freelancer/saved-searches",search_payload,t1)
    with ThreadPoolExecutor(max_workers=2) as ex:
        first=ex.submit(save_same_search);second=ex.submit(save_same_search)
        search_results=[first.result(),second.result()]
    assert sorted(x[0] for x in search_results)==[200,201],search_results
    search_ids={int(x[1]["id"]) for x in search_results}
    assert len(search_ids)==1,search_results
    assert sum(1 for _,payload in search_results if payload.get("idempotent_replay"))==1,search_results
    saved_searches=call("GET","/api/v1/freelancer/saved-searches",token=t1,expected=(200,)).get("items") or []
    assert len([x for x in saved_searches if int(x["id"]) in search_ids])==1,saved_searches
    changed_search=dict(search_payload);changed_search["name"]="Changed name same key"
    changed_result=raw_call("POST","/api/v1/freelancer/saved-searches",changed_search,t1)
    assert changed_result[0]==409 and changed_result[1].get("error")=="idempotency_key_reused",changed_result

    # Concurrent double-submit with the same idempotency key creates one task and one attachment.
    idem_key=f"task-race-{base}"
    idem_payload={
        "category_id":cats[0]["id"],"title":"اختبار منع تكرار إنشاء المهمة",
        "description":"اختبار آلي للتأكد أن الضغط المزدوج أو إعادة نفس الطلب لا ينشئ مهمتين.",
        "budget_min":"100","budget_max":"180","urgency":"normal",
        "idempotency_key":idem_key,
        "attachments":[{"name":"مرجع اختبار.pdf","url":"https://example.com/minjaz-idempotency.pdf","mime_type":"application/pdf","size_bytes":1234}],
    }
    idem_barrier=Barrier(2)
    def create_same_task():
        idem_barrier.wait()
        return raw_call("POST","/api/v1/tasks",idem_payload,ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        first=ex.submit(create_same_task);second=ex.submit(create_same_task)
        idem_results=[first.result(),second.result()]
    assert sorted(x[0] for x in idem_results)==[200,201],idem_results
    ids={int(x[1]["id"]) for x in idem_results}
    assert len(ids)==1,idem_results
    replay=next(x[1] for x in idem_results if x[0]==200)
    assert replay.get("idempotent_replay") is True,replay
    idem_task_id=next(iter(ids))
    idem_files=call("GET",f"/api/v1/tasks/{idem_task_id}/attachments",token=ct,expected=(200,)).get("items") or []
    assert len(idem_files)==1,idem_files
    changed=dict(idem_payload);changed["title"]="عنوان مختلف بنفس المفتاح"
    reused=raw_call("POST","/api/v1/tasks",changed,ct)
    assert reused[0]==409 and reused[1].get("error")=="idempotency_key_reused",reused

    repeat_key=f"repeat-race-{base}"
    repeat_payload={"idempotency_key":repeat_key}
    repeat_barrier=Barrier(2)
    def repeat_same_task():
        repeat_barrier.wait()
        return raw_call("POST",f"/api/v1/tasks/{idem_task_id}/repeat",repeat_payload,ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        first=ex.submit(repeat_same_task);second=ex.submit(repeat_same_task)
        repeat_results=[first.result(),second.result()]
    assert sorted(x[0] for x in repeat_results)==[200,201],repeat_results
    repeat_ids={int(x[1]["id"]) for x in repeat_results}
    assert len(repeat_ids)==1,repeat_results
    repeat_replay=next(x[1] for x in repeat_results if x[0]==200)
    assert repeat_replay.get("idempotent_replay") is True,repeat_replay
    call("POST",f"/api/v1/tasks/{idem_task_id}/close",{},ct,expected=(200,))

    # A client can close an open task; sent proposals are rejected and no new proposal can appear afterward.
    close_task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار إغلاق مهمة مفتوحة",
        "description":"اختبار آلي لإغلاق المهمة قبل اختيار مستقل ومنع عروض جديدة بعدها.",
        "budget_min":"90","budget_max":"170","urgency":"normal"
    },ct)
    close_prop=call("POST",f"/api/v1/tasks/{close_task['id']}/proposals",{
        "price":"115.00","delivery_hours":20,"revisions":1,"message":"عرض قبل الإغلاق"
    },t1)
    closed=call("POST",f"/api/v1/tasks/{close_task['id']}/close",{},ct,expected=(200,))
    assert closed.get("status")=="cancelled",closed
    own_tasks=call("GET","/api/v1/tasks",token=ct,expected=(200,)).get("items") or []
    closed_row=next(x for x in own_tasks if int(x["id"])==int(close_task["id"]))
    assert closed_row["status"]=="cancelled",closed_row
    closed_props=call("GET",f"/api/v1/tasks/{close_task['id']}/proposals",token=ct,expected=(200,)).get("items") or []
    assert any(int(x["id"])==int(close_prop["id"]) and x["status"]=="rejected" for x in closed_props),closed_props
    late_prop=raw_call("POST",f"/api/v1/tasks/{close_task['id']}/proposals",{
        "price":"119.00","delivery_hours":18,"revisions":1,"message":"عرض متأخر"
    },t2)
    assert late_prop[0]==404 and late_prop[1].get("error")=="task_not_found",late_prop

    # Closing and creating a proposal at the same moment cannot leave a sent proposal on a cancelled task.
    close_write_task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سباق الإغلاق والعرض",
        "description":"اختبار آلي لتزامن إغلاق المهمة مع إرسال عرض جديد.",
        "budget_min":"100","budget_max":"190","urgency":"normal"
    },ct)
    close_write_barrier=Barrier(2)
    def close_write():
        close_write_barrier.wait()
        return raw_call("POST",f"/api/v1/tasks/{close_write_task['id']}/close",{},ct)
    def create_during_close():
        close_write_barrier.wait()
        return raw_call("POST",f"/api/v1/tasks/{close_write_task['id']}/proposals",{
            "price":"121.00","delivery_hours":19,"revisions":1,"message":"عرض متزامن مع الإغلاق"
        },t1)
    with ThreadPoolExecutor(max_workers=2) as ex:
        fc=ex.submit(close_write);fp=ex.submit(create_during_close)
        close_write_result,proposal_write_result=fc.result(),fp.result()
    assert close_write_result[0]==200,close_write_result
    assert proposal_write_result[0] in (201,404),proposal_write_result
    if proposal_write_result[0]==404:
        assert proposal_write_result[1].get("error")=="task_not_found",proposal_write_result
    final_close_props=call("GET",f"/api/v1/tasks/{close_write_task['id']}/proposals",token=ct,expected=(200,)).get("items") or []
    assert all(x.get("status")!="sent" for x in final_close_props),final_close_props

    # Closing and accepting the same task at once has one winner: either a closed task or a created order.
    close_accept_task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سباق الإغلاق والاختيار",
        "description":"اختبار آلي لتزامن إغلاق المهمة مع اختيار عرض مستقل.",
        "budget_min":"100","budget_max":"200","urgency":"normal"
    },ct)
    close_accept_prop=call("POST",f"/api/v1/tasks/{close_accept_task['id']}/proposals",{
        "price":"130.00","delivery_hours":22,"revisions":2,"message":"عرض سباق الإغلاق"
    },t2)
    close_accept_barrier=Barrier(2)
    def close_accept_close():
        close_accept_barrier.wait()
        return raw_call("POST",f"/api/v1/tasks/{close_accept_task['id']}/close",{},ct)
    def close_accept_order():
        close_accept_barrier.wait()
        return raw_call("POST","/api/v1/orders",{"proposal_id":close_accept_prop["id"]},ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        fc=ex.submit(close_accept_close);fa=ex.submit(close_accept_order)
        close_accept_result,accept_close_result=fc.result(),fa.result()
    assert (close_accept_result[0],accept_close_result[0]) in ((200,409),(409,201)),(close_accept_result,accept_close_result)
    if close_accept_result[0]==409:
        assert close_accept_result[1].get("error")=="task_has_order",close_accept_result
    if accept_close_result[0]==409:
        assert accept_close_result[1].get("error")=="proposal_not_available",accept_close_result

    # A freelancer can withdraw an open proposal, and withdrawal is serialized with client acceptance.
    withdraw_task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سحب العرض",
        "description":"اختبار آلي للتأكد من سحب العرض قبل الاختيار ومنع السباق مع قبول العميل.",
        "budget_min":"80","budget_max":"160","urgency":"normal"
    },ct)
    withdrawn_proposal=call("POST",f"/api/v1/tasks/{withdraw_task['id']}/proposals",{
        "price":"99.00","delivery_hours":12,"revisions":1,"message":"عرض قابل للسحب"
    },t1)
    withdrawn=call("DELETE",f"/api/v1/tasks/{withdraw_task['id']}/proposals",token=t1,expected=(200,))
    assert withdrawn.get("withdrawn") is True and int(withdrawn.get("proposal_id"))==int(withdrawn_proposal["id"]),withdrawn
    remaining=call("GET",f"/api/v1/tasks/{withdraw_task['id']}/proposals",token=t1,expected=(200,)).get("items") or []
    assert not remaining,remaining

    race_task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سباق سحب وقبول العرض",
        "description":"اختبار آلي لقفل المهمة والعرض عند السحب والقبول المتزامنين.",
        "budget_min":"100","budget_max":"180","urgency":"normal"
    },ct)
    race_proposal=call("POST",f"/api/v1/tasks/{race_task['id']}/proposals",{
        "price":"110.00","delivery_hours":18,"revisions":1,"message":"عرض سباق السحب"
    },t2)
    withdraw_barrier=Barrier(2)
    def withdraw_race():
        withdraw_barrier.wait()
        return raw_call("DELETE",f"/api/v1/tasks/{race_task['id']}/proposals",token=t2)
    def accept_race():
        withdraw_barrier.wait()
        return raw_call("POST","/api/v1/orders",{"proposal_id":race_proposal["id"]},ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        fw=ex.submit(withdraw_race);fa=ex.submit(accept_race)
        withdraw_result,accept_result=fw.result(),fa.result()
    assert (withdraw_result[0],accept_result[0]) in ((200,404),(409,201)),(withdraw_result,accept_result)
    if withdraw_result[0]==409:assert withdraw_result[1].get("error")=="proposal_locked",withdraw_result
    if accept_result[0]==404:assert accept_result[1].get("error")=="proposal_not_found",accept_result

    task=call("POST","/api/v1/tasks",{
        "category_id":cats[0]["id"],"title":"اختبار سباق قبول العروض والدفع",
        "description":"اختبار آلي للتأكد من إنشاء طلب واحد فقط ومنع تكرار أثر الدفع عند الطلبات المتزامنة.",
        "budget_min":"100","budget_max":"200","urgency":"normal"
    },ct)

    p1=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"120.00","delivery_hours":24,"revisions":1,"message":"عرض A"
    },t1)
    p2=call("POST",f"/api/v1/tasks/{task['id']}/proposals",{
        "price":"125.00","delivery_hours":24,"revisions":1,"message":"عرض B"
    },t2)

    barrier=Barrier(2)
    def accept(item):
        label,pid=item
        barrier.wait()
        return label,raw_call("POST","/api/v1/orders",{"proposal_id":pid},ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        created=list(ex.map(accept,[("a",p1["id"]),("b",p2["id"])]))

    assert sorted(x[1][0] for x in created)==[201,409],created
    winner_label,winner_http=next((label,res) for label,res in created if res[0]==201)
    loser_payload=next(res[1] for label,res in created if res[0]==409)
    assert loser_payload.get("error")=="order_exists",loser_payload
    order=winner_http[1]

    orders=call("GET","/api/v1/orders",token=ct,expected=(200,)).get("items") or []
    same_task=[x for x in orders if int(x["task_id"])==int(task["id"])]
    assert len(same_task)==1,same_task
    assert int(same_task[0]["id"])==int(order["id"]),same_task

    repeat_pid=p1["id"] if winner_label=="a" else p2["id"]
    repeat=raw_call("POST","/api/v1/orders",{"proposal_id":repeat_pid},ct)
    assert repeat[0]==409 and repeat[1].get("error")=="order_exists",repeat

    pay_barrier=Barrier(2)
    def pay(_):
        pay_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/pay",{},ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        payments=list(ex.map(pay,(1,2)))

    assert [x[0] for x in payments]==[200,200],payments
    assert sum(1 for _,p in payments if p.get("already_paid"))==1,payments
    assert sum(1 for _,p in payments if p.get("mode")=="mock" and not p.get("already_paid"))==1,payments

    final_order=call("GET",f"/api/v1/orders/{order['id']}",token=ct,expected=(200,))
    assert final_order["status"]=="in_progress" and final_order["payment_status"]=="paid",final_order

    timeline=call("GET",f"/api/v1/orders/{order['id']}/timeline",token=ct,expected=(200,)).get("items") or []
    payment_events=[x for x in timeline if x.get("type")=="payment"]
    assert len(payment_events)==1,payment_events

    winner_token=t1 if int(order["freelancer_id"])==int(f1["user"]["id"]) else t2
    notes=call("GET","/api/v1/notifications?kind=payment&limit=50",token=winner_token,expected=(200,)).get("items") or []
    payment_notes=[x for x in notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(payment_notes)==1,payment_notes

    # Double-send/retry of the same chat message creates one message, one attachment and one notification.
    message_key=f"msg-race-{base}"
    message_payload={
        "body":"رسالة ثابتة لاختبار منع التكرار",
        "idempotency_key":message_key,
        "attachments":[{"name":"مرفق رسالة.pdf","url":"https://example.com/minjaz-message.pdf","mime_type":"application/pdf","size_bytes":4321}],
    }
    message_barrier=Barrier(2)
    def send_same_message(_):
        message_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/messages",message_payload,ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        message_results=list(ex.map(send_same_message,(1,2)))
    assert sorted(x[0] for x in message_results)==[200,201],message_results
    message_ids={int(x[1]["id"]) for x in message_results}
    assert len(message_ids)==1,message_results
    message_replay=next(x[1] for x in message_results if x[0]==200)
    assert message_replay.get("idempotent_replay") is True,message_replay
    chat=call("GET",f"/api/v1/orders/{order['id']}/messages",token=ct,expected=(200,)).get("items") or []
    stable=[x for x in chat if x.get("body")=="رسالة ثابتة لاختبار منع التكرار"]
    assert len(stable)==1 and len(stable[0].get("attachments") or [])==1,stable
    message_notes=call("GET","/api/v1/notifications?kind=message&limit=50",token=winner_token,expected=(200,)).get("items") or []
    message_notes=[x for x in message_notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(message_notes)==1,message_notes
    changed_message=dict(message_payload);changed_message["body"]="رسالة مختلفة بنفس المفتاح"
    message_conflict=raw_call("POST",f"/api/v1/orders/{order['id']}/messages",changed_message,ct)
    assert message_conflict[0]==409 and message_conflict[1].get("error")=="idempotency_key_reused",message_conflict

    # Concurrent delivery retries create one delivery, one attachment and one notification.
    delivery_key=f"deliver-race-{base}"
    delivery_payload={
        "note":"تسليم ثابت لاختبار منع التكرار",
        "idempotency_key":delivery_key,
        "attachments":[{"name":"مرفق تسليم.pdf","url":"https://example.com/minjaz-delivery.pdf","mime_type":"application/pdf","size_bytes":3456}],
    }
    delivery_barrier=Barrier(2)
    def deliver_same(_):
        delivery_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/deliver",delivery_payload,winner_token)
    with ThreadPoolExecutor(max_workers=2) as ex:
        delivery_results=list(ex.map(deliver_same,(1,2)))
    assert sorted(x[0] for x in delivery_results)==[200,201],delivery_results
    delivery_ids={int(x[1]["delivery"]["id"]) for x in delivery_results}
    assert len(delivery_ids)==1,delivery_results
    assert sum(1 for _,x in delivery_results if x.get("idempotent_replay"))==1,delivery_results
    deliveries=call("GET",f"/api/v1/orders/{order['id']}/deliveries",token=ct,expected=(200,)).get("items") or []
    stable_deliveries=[x for x in deliveries if x.get("note")=="تسليم ثابت لاختبار منع التكرار"]
    assert len(stable_deliveries)==1 and len(stable_deliveries[0].get("attachments") or [])==1,stable_deliveries
    delivery_notes=call("GET","/api/v1/notifications?kind=delivery&limit=50",token=ct,expected=(200,)).get("items") or []
    delivery_notes=[x for x in delivery_notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(delivery_notes)==1,delivery_notes
    changed_delivery=dict(delivery_payload);changed_delivery["note"]="تسليم مختلف بنفس المفتاح"
    delivery_conflict=raw_call("POST",f"/api/v1/orders/{order['id']}/deliver",changed_delivery,winner_token)
    assert delivery_conflict[0]==409 and delivery_conflict[1].get("error")=="idempotency_key_reused",delivery_conflict

    # Concurrent revision retries create one revision, one implicit chat entry and one notification.
    revision_key=f"revision-race-{base}"
    revision_payload={"note":"تعديل ثابت لاختبار منع التكرار","idempotency_key":revision_key}
    revision_barrier=Barrier(2)
    def revise_same(_):
        revision_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/revision",revision_payload,ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        revision_results=list(ex.map(revise_same,(1,2)))
    assert [x[0] for x in revision_results]==[200,200],revision_results
    revision_ids={int(x[1]["revision"]["id"]) for x in revision_results}
    assert len(revision_ids)==1,revision_results
    assert sum(1 for _,x in revision_results if x.get("idempotent_replay"))==1,revision_results
    revisions=call("GET",f"/api/v1/orders/{order['id']}/revisions",token=ct,expected=(200,)).get("items") or []
    stable_revisions=[x for x in revisions if x.get("note")=="تعديل ثابت لاختبار منع التكرار"]
    assert len(stable_revisions)==1,stable_revisions
    revision_chat=call("GET",f"/api/v1/orders/{order['id']}/messages",token=ct,expected=(200,)).get("items") or []
    implicit=[x for x in revision_chat if "تعديل ثابت لاختبار منع التكرار" in str(x.get("body") or "")]
    assert len(implicit)==1,implicit
    revision_notes=call("GET","/api/v1/notifications?kind=revision&limit=50",token=winner_token,expected=(200,)).get("items") or []
    revision_notes=[x for x in revision_notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(revision_notes)==1,revision_notes
    changed_revision=dict(revision_payload);changed_revision["note"]="تعديل مختلف بنفس المفتاح"
    revision_conflict=raw_call("POST",f"/api/v1/orders/{order['id']}/revision",changed_revision,ct)
    assert revision_conflict[0]==409 and revision_conflict[1].get("error")=="idempotency_key_reused",revision_conflict

    # Re-deliver after the revision so completion and review can continue.
    call("POST",f"/api/v1/orders/{order['id']}/deliver",{"note":"تسليم بعد تنفيذ التعديل."},winner_token)
    complete_key=f"complete-race-{base}"
    complete_payload={"idempotency_key":complete_key}
    complete_barrier=Barrier(2)
    def complete_same(_):
        complete_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/complete",complete_payload,ct)
    with ThreadPoolExecutor(max_workers=2) as ex:
        complete_results=list(ex.map(complete_same,(1,2)))
    assert [x[0] for x in complete_results]==[200,200],complete_results
    assert sum(1 for _,x in complete_results if x.get("idempotent_replay"))==1,complete_results
    completed_order=call("GET",f"/api/v1/orders/{order['id']}",token=ct,expected=(200,))
    assert completed_order.get("status")=="completed",completed_order
    completed_notes=call("GET","/api/v1/notifications?kind=completed&limit=50",token=winner_token,expected=(200,)).get("items") or []
    completed_notes=[x for x in completed_notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(completed_notes)==1,completed_notes

    # Complete the same order and verify concurrent identical reviews are idempotent.
    review_payload={"quality":5,"timeliness":4,"communication":5,"comment":"تقييم ثابت لاختبار التزامن"}
    review_barrier=Barrier(2)
    def review(_):
        review_barrier.wait()
        return raw_call("POST",f"/api/v1/orders/{order['id']}/review",review_payload,ct)

    with ThreadPoolExecutor(max_workers=2) as ex:
        review_results=list(ex.map(review,(1,2)))

    assert sorted(x[0] for x in review_results)==[200,201],review_results
    review_bodies=[x[1] for x in review_results]
    assert sum(1 for x in review_bodies if x.get("state")=="created")==1,review_bodies
    assert sum(1 for x in review_bodies if x.get("state")=="unchanged")==1,review_bodies

    review_notes=call("GET","/api/v1/notifications?kind=review&limit=50",token=winner_token,expected=(200,)).get("items") or []
    review_notes=[x for x in review_notes if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(review_notes)==1,review_notes
    assert review_notes[0].get("title")=="وصلك تقييم جديد",review_notes

    same=call("POST",f"/api/v1/orders/{order['id']}/review",review_payload,ct,expected=(200,))
    assert same.get("state")=="unchanged" and same.get("updated") is False,same
    review_notes_same=call("GET","/api/v1/notifications?kind=review&limit=50",token=winner_token,expected=(200,)).get("items") or []
    review_notes_same=[x for x in review_notes_same if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(review_notes_same)==1,review_notes_same

    updated=call("POST",f"/api/v1/orders/{order['id']}/review",{
        "quality":4,"timeliness":4,"communication":5,"comment":"تم تعديل التقييم مرة واحدة"
    },ct,expected=(200,))
    assert updated.get("state")=="updated" and updated.get("updated") is True,updated
    review_notes_updated=call("GET","/api/v1/notifications?kind=review&limit=50",token=winner_token,expected=(200,)).get("items") or []
    review_notes_updated=[x for x in review_notes_updated if int(x.get("order_id") or 0)==int(order["id"])]
    assert len(review_notes_updated)==2,review_notes_updated
    assert any(x.get("title")=="تم تحديث تقييمك" for x in review_notes_updated),review_notes_updated

    reviewed_order=call("GET",f"/api/v1/orders/{order['id']}",token=ct,expected=(200,))
    assert int(reviewed_order["review_quality"])==4,reviewed_order
    assert int(reviewed_order["review_timeliness"])==4,reviewed_order
    assert int(reviewed_order["review_communication"])==5,reviewed_order
    assert reviewed_order["review_comment"]=="تم تعديل التقييم مرة واحدة",reviewed_order

    return {
        "ok":True,"version":health.get("version"),"task_creation_idempotent":True,
        "task_repeat_idempotent":True,
        "task_close_supported":True,
        "task_close_proposal_write_race_safe":True,
        "task_close_accept_race_safe":True,
        "proposal_withdrawal_supported":True,
        "proposal_withdraw_accept_race_safe":True,
        "single_order_under_concurrency":True,
        "stable_order_conflict":True,
        "mock_payment_idempotent":True,
        "single_payment_event":True,
        "single_payment_notification":True,
        "message_send_idempotent":True,
        "single_message_notification":True,
        "delivery_retry_idempotent":True,
        "single_delivery_notification":True,
        "revision_retry_idempotent":True,
        "single_revision_notification":True,
        "complete_retry_idempotent":True,
        "single_complete_notification":True,
        "concurrent_identical_review_idempotent":True,
        "single_initial_review_notification":True,
        "unchanged_review_no_side_effect":True,
        "review_update_supported":True,
        "single_review_update_notification":True,
        "order_id":order["id"],"task_id":task["id"],"winning_proposal":winner_label
    }

RESULT=run()
print("MINJAZ_ORDER_CREATE_PAYMENT_E2E_OK",json.dumps(RESULT,ensure_ascii=False),flush=True)
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
