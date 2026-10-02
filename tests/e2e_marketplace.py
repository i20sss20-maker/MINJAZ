import json
import os
import random
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.getenv("E2E_BASE_URL", "https://minjaz-stage-source-production.up.railway.app").rstrip("/")
PORT = int(os.getenv("PORT", "3000"))


def call(method, path, body=None, token=None, expected=(200, 201)):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
            payload = json.loads(raw or b"{}")
            if resp.status not in expected:
                raise AssertionError((path, resp.status, payload))
            return payload
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")}
        raise AssertionError((path, exc.code, payload)) from exc


def login(phone, role, name):
    challenge = call("POST", "/api/v1/auth/request-otp", {"phone": phone})
    code = challenge.get("dev_code") or "1234"
    out = call(
        "POST",
        "/api/v1/auth/verify-otp",
        {
            "challenge_id": challenge["challenge_id"],
            "code": code,
            "role": role,
            "name": name,
        },
    )
    effective_roles = out.get("roles") or out.get("user", {}).get("roles") or [out.get("user", {}).get("role")]
    assert out.get("token"), out
    assert role in effective_roles, out
    return out["token"]


def run():
    health = call("GET", "/health", expected=(200,))
    assert health.get("ok") is True, health
    assert health.get("database") is True, health
    assert health.get("version") == "0.5.5-rc5", health

    readiness = call("GET", "/readiness", expected=(200,))
    assert readiness.get("ready_for_beta") is True, readiness

    categories = call("GET", "/api/v1/categories", expected=(200,)).get("items") or []
    services = call("GET", "/api/v1/services", expected=(200,)).get("items") or []
    assert categories, "categories_empty"
    assert services, "services_empty"

    suffix = f"{int(time.time()) % 1000000:06d}{random.randint(10,99)}"
    client_phone = "+9665" + suffix
    freelancer_phone = "+9666" + suffix

    client_token = login(client_phone, "client", "E2E Client")
    freelancer_token = login(freelancer_phone, "freelancer", "E2E Freelancer")

    client_me = call("GET", "/api/v1/me", token=client_token, expected=(200,))
    freelancer_me = call("GET", "/api/v1/me", token=freelancer_token, expected=(200,))
    assert client_me["user"]["role"] == "client"
    assert freelancer_me["user"]["role"] == "freelancer"

    task = call(
        "POST",
        "/api/v1/tasks",
        {
            "category_id": categories[0]["id"],
            "title": "اختبار دورة إنجاز متكاملة",
            "description": "هذه مهمة اختبار آلي للتأكد من دورة العمل الكاملة داخل منصة منجاز من إنشاء المهمة حتى التقييم النهائي.",
            "budget_min": 100,
            "budget_max": 180,
            "urgency": "normal",
        },
        client_token,
    )
    task_id = task["id"]

    opportunities = call("GET", "/api/v1/tasks", token=freelancer_token, expected=(200,)).get("items") or []
    assert any(int(item["id"]) == int(task_id) for item in opportunities), "task_not_visible"

    proposal = call(
        "POST",
        f"/api/v1/tasks/{task_id}/proposals",
        {
            "price": 120,
            "delivery_hours": 24,
            "revisions": 2,
            "message": "عرض اختبار آلي متكامل.",
        },
        freelancer_token,
    )
    proposal_id = proposal["id"]

    # Client can invite the freelancer to the open task and freelancer receives the invitation.
    invite = call(
        "POST",
        f"/api/v1/freelancers/{freelancer_me['user']['id']}/invite",
        {"task_id": task_id, "note": "دعوة اختبار للمستقل قبل اعتماد العرض."},
        client_token,
    )
    assert int(invite["task_id"]) == int(task_id), invite
    invite_notifications = call(
        "GET",
        "/api/v1/notifications?kind=task_invite&unread=1",
        token=freelancer_token,
        expected=(200,),
    )
    assert any(int(item.get("task_id") or 0) == int(task_id) for item in (invite_notifications.get("items") or [])), invite_notifications

    proposals = call(
        "GET",
        f"/api/v1/tasks/{task_id}/proposals",
        token=client_token,
        expected=(200,),
    ).get("items") or []
    assert any(int(item["id"]) == int(proposal_id) for item in proposals), "proposal_not_visible"

    order = call("POST", "/api/v1/orders", {"proposal_id": proposal_id}, client_token)
    order_id = order["id"]
    assert order["status"] == "awaiting_payment", order

    paid = call("POST", f"/api/v1/orders/{order_id}/pay", {}, client_token)
    assert paid.get("ok") is True and paid.get("mode") == "mock", paid

    call(
        "POST",
        f"/api/v1/orders/{order_id}/messages",
        {"body": "رسالة اختبار بين العميل والمستقل."},
        client_token,
    )
    messages = call(
        "GET",
        f"/api/v1/orders/{order_id}/messages",
        token=freelancer_token,
        expected=(200,),
    ).get("items") or []
    assert any("رسالة اختبار" in (item.get("body") or "") for item in messages)

    delivery = call(
        "POST",
        f"/api/v1/orders/{order_id}/deliver",
        {"note": "تم إنجاز وتسليم اختبار الدورة كاملة."},
        freelancer_token,
    )
    assert delivery.get("ok") is True, delivery

    revision = call(
        "POST",
        f"/api/v1/orders/{order_id}/revision",
        {"note": "تعديل اختبار واحد للتأكد من دورة المراجعات."},
        client_token,
    )
    assert revision.get("ok") is True, revision

    redelivery = call(
        "POST",
        f"/api/v1/orders/{order_id}/deliver",
        {"note": "تم تنفيذ التعديل وإعادة التسليم."},
        freelancer_token,
    )
    assert redelivery.get("ok") is True, redelivery

    completed = call("POST", f"/api/v1/orders/{order_id}/complete", {}, client_token)
    assert completed.get("ok") is True, completed

    review = call(
        "POST",
        f"/api/v1/orders/{order_id}/review",
        {
            "quality": 5,
            "timeliness": 5,
            "communication": 5,
            "comment": "تقييم اختبار آلي ناجح.",
        },
        client_token,
    )
    assert review.get("ok") is True, review

    # After a shared order exists, client can keep the freelancer in the trusted team.
    team_add = call(
        "POST",
        f"/api/v1/team/{freelancer_me['user']['id']}",
        {"note": "مستقل موثوق من اختبار الدورة المتكاملة."},
        client_token,
    )
    assert team_add.get("ok") is True, team_add
    team = call("GET", "/api/v1/team", token=client_token, expected=(200,)).get("items") or []
    assert any(int(item["freelancer_id"]) == int(freelancer_me["user"]["id"]) for item in team), team

    final_order = call(
        "GET",
        f"/api/v1/orders/{order_id}",
        token=client_token,
        expected=(200,),
    )
    assert final_order["status"] == "completed", final_order
    assert final_order["payment_status"] == "paid", final_order
    assert final_order.get("review_id"), final_order

    earnings = call(
        "GET",
        "/api/v1/freelancer/earnings",
        token=freelancer_token,
        expected=(200,),
    )
    notifications = call(
        "GET",
        "/api/v1/notifications",
        token=freelancer_token,
        expected=(200,),
    )
    assert "available_balance" in earnings, earnings
    assert isinstance(notifications.get("items"), list), notifications
    assert int(notifications.get("unread") or 0) > 0, notifications
    call("POST", "/api/v1/notifications/read-all", {}, freelancer_token, expected=(200,))
    after_read = call(
        "GET",
        "/api/v1/notifications?unread=1",
        token=freelancer_token,
        expected=(200,),
    )
    assert int(after_read.get("unread") or 0) == 0 and not (after_read.get("items") or []), after_read

    return {
        "ok": True,
        "version": health["version"],
        "ready_for_beta": True,
        "auth": True,
        "tasks": True,
        "proposals": True,
        "orders": True,
        "payment_mock": True,
        "messages": True,
        "delivery": True,
        "revision": True,
        "completion": True,
        "review": True,
        "earnings": True,
        "notifications": True,
        "task_invite": True,
        "trusted_team": True,
        "notifications_read_all": True,
        "task_id": task_id,
        "order_id": order_id,
    }


RESULT = run()
print("MINJAZ_MARKETPLACE_E2E_OK", json.dumps(RESULT, ensure_ascii=False), flush=True)

if os.getenv("E2E_EXIT_AFTER_RUN") == "1":
    raise SystemExit(0)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(RESULT, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

# trigger Railway e2e deployment

# run against fixed stage target
