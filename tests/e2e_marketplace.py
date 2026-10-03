import json
import os
import random
import time
import urllib.error
import urllib.request
import hashlib
import psycopg2
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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
        if exc.code in expected:
            return payload
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

    def activity_count(token, event_type):
        items = call("GET", "/api/v1/account/activity", token=token, expected=(200,)).get("items") or []
        return sum(1 for x in items if x.get("event_type") == event_type)

    # Retried account updates must not duplicate security/account activity.
    profile_before = activity_count(client_token, "profile_updated")
    profile_first = call("PATCH", "/api/v1/me/profile", {"name": "E2E Client Updated"}, client_token, expected=(200,))
    profile_retry = call("PATCH", "/api/v1/me/profile", {"name": "E2E Client Updated"}, client_token, expected=(200,))
    assert profile_first.get("idempotent_replay") is False, profile_first
    assert profile_retry.get("idempotent_replay") is True, profile_retry
    assert activity_count(client_token, "profile_updated") == profile_before + 1

    prefs = call("GET", "/api/v1/account/preferences", token=client_token, expected=(200,))
    next_marketing = not bool(prefs.get("marketing"))
    prefs_before = activity_count(client_token, "preferences_updated")
    prefs_first = call("PATCH", "/api/v1/account/preferences", {"marketing": next_marketing}, client_token, expected=(200,))
    prefs_retry = call("PATCH", "/api/v1/account/preferences", {"marketing": next_marketing}, client_token, expected=(200,))
    assert prefs_first.get("idempotent_replay") is False, prefs_first
    assert prefs_retry.get("idempotent_replay") is True, prefs_retry
    assert prefs_first.get("updated_at") == prefs_retry.get("updated_at"), (prefs_first, prefs_retry)
    assert activity_count(client_token, "preferences_updated") == prefs_before + 1

    role_before = activity_count(client_token, "role_switched")
    same_role = call("PATCH", "/api/v1/me/active-role", {"role": "client"}, client_token, expected=(200,))
    assert same_role.get("idempotent_replay") is True, same_role
    assert activity_count(client_token, "role_switched") == role_before

    def seed_session(user_id, tag):
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            with conn:
                with conn.cursor() as cur:
                    raw = f"{suffix}-{tag}-{random.random()}".encode("utf-8")
                    token_hash = hashlib.sha256(raw).hexdigest()
                    cur.execute(
                        "insert into sessions(user_id,token_hash,expires_at,device_label,last_seen_at) values(%s,%s,now()+interval '1 day',%s,now()) returning id",
                        (user_id, token_hash, f"E2E {tag}"),
                    )
                    return int(cur.fetchone()[0])
        finally:
            conn.close()

    # Revoking an already revoked session is a successful replay, not a false 404.
    target_id = seed_session(client_me["user"]["id"], "extra-device")
    revoked_before = activity_count(client_token, "session_revoked")
    first_revoke = call("DELETE", f"/api/v1/account/sessions/{target_id}", token=client_token, expected=(200,))
    retry_revoke = call("DELETE", f"/api/v1/account/sessions/{target_id}", token=client_token, expected=(200,))
    assert first_revoke.get("idempotent_replay") is False, first_revoke
    assert retry_revoke.get("idempotent_replay") is True, retry_revoke
    assert activity_count(client_token, "session_revoked") == revoked_before + 1

    # Revoke-others records activity only when at least one active session actually changed.
    seed_session(client_me["user"]["id"], "other-device-a")
    seed_session(client_me["user"]["id"], "other-device-b")
    others_before = activity_count(client_token, "sessions_revoked")
    revoke_others = call("POST", "/api/v1/account/sessions/revoke-others", {}, client_token, expected=(200,))
    revoke_others_retry = call("POST", "/api/v1/account/sessions/revoke-others", {}, client_token, expected=(200,))
    assert int(revoke_others.get("revoked_count") or 0) >= 2, revoke_others
    assert revoke_others.get("idempotent_replay") is False, revoke_others
    assert int(revoke_others_retry.get("revoked_count") or 0) == 0, revoke_others_retry
    assert revoke_others_retry.get("idempotent_replay") is True, revoke_others_retry
    assert activity_count(client_token, "sessions_revoked") == others_before + 1

    # Onboarding must work for both roles against the real schema.
    client_onboarding = call("GET", "/api/v1/onboarding", token=client_token, expected=(200,))
    freelancer_onboarding = call("GET", "/api/v1/onboarding", token=freelancer_token, expected=(200,))
    assert client_onboarding["role"] == "client" and isinstance(client_onboarding.get("steps"), list), client_onboarding
    assert freelancer_onboarding["role"] == "freelancer" and isinstance(freelancer_onboarding.get("steps"), list), freelancer_onboarding
    assert any(x.get("key") == "portfolio" for x in freelancer_onboarding["steps"]), freelancer_onboarding

    # Starting a new marketplace commitment requires current legal acceptance.
    blocked_task = call(
        "POST",
        "/api/v1/tasks",
        {
            "category_id": categories[0]["id"],
            "title": "مهمة يجب رفضها قبل الموافقة",
            "description": "اختبار آلي للتأكد أن المنصة تمنع بدء تعامل جديد قبل قبول المستندات القانونية الحالية.",
            "budget_min": 100,
            "budget_max": 150,
            "urgency": "normal",
        },
        client_token,
        expected=(428,),
    )
    assert blocked_task.get("error") == "legal_acceptance_required", blocked_task
    assert set(blocked_task.get("missing_documents") or []) == {"terms", "privacy", "marketplace_rules"}, blocked_task

    client_accepted = call(
        "POST",
        "/api/v1/legal/accept",
        {"documents": ["terms", "privacy", "marketplace_rules"]},
        client_token,
        expected=(200,),
    )
    assert client_accepted.get("complete") is True, client_accepted

    gate_task = call(
        "POST",
        "/api/v1/tasks",
        {
            "category_id": categories[0]["id"],
            "title": "مهمة بوابة الموافقة القانونية",
            "description": "مهمة مؤقتة لاختبار رفض عرض المستقل قبل موافقته على المستندات القانونية الحالية.",
            "budget_min": 100,
            "budget_max": 150,
            "urgency": "normal",
        },
        client_token,
    )
    blocked_proposal = call(
        "POST",
        f"/api/v1/tasks/{gate_task['id']}/proposals",
        {"price": 110, "delivery_hours": 24, "revisions": 1, "message": "يجب رفض هذا العرض قبل الموافقة."},
        freelancer_token,
        expected=(428,),
    )
    assert blocked_proposal.get("error") == "legal_acceptance_required", blocked_proposal
    call("POST", f"/api/v1/tasks/{gate_task['id']}/close", {}, client_token, expected=(200,))

    freelancer_accepted = call(
        "POST",
        "/api/v1/legal/accept",
        {"documents": ["terms", "privacy", "marketplace_rules"]},
        freelancer_token,
        expected=(200,),
    )
    assert freelancer_accepted.get("complete") is True, freelancer_accepted

    freelancer_profile = call(
        "PATCH",
        "/api/v1/freelancer/profile",
        {
            "bio": "مستقل اختبار متكامل متخصص في تنفيذ المهام الرقمية باحتراف ووضوح.",
            "skills": ["تصميم", "PowerPoint", "Canva"],
            "is_available": True,
        },
        freelancer_token,
        expected=(200,),
    )
    assert len(freelancer_profile.get("skills") or []) >= 3, freelancer_profile

    client_profile = call(
        "PATCH",
        "/api/v1/client/profile",
        {
            "company_name": "MINJAZ E2E Client",
            "city": "Riyadh",
            "sector": "Digital Services",
            "bio": "ملف عميل تجريبي لاختبار رحلة الإعداد الكاملة.",
        },
        client_token,
        expected=(200,),
    )
    assert client_profile.get("company_name") == "MINJAZ E2E Client", client_profile

    portfolio_payload = {
        "title": "نموذج عمل E2E",
        "description": "نموذج تجريبي للتأكد من اكتمال خطوة معرض الأعمال.",
        "external_url": "https://example.com/minjaz-e2e-work",
        "idempotency_key": f"portfolio-{suffix}",
    }
    portfolio = call("POST", "/api/v1/freelancer/portfolio", portfolio_payload, freelancer_token)
    assert portfolio.get("id"), portfolio
    portfolio_retry = call("POST", "/api/v1/freelancer/portfolio", portfolio_payload, freelancer_token)
    assert int(portfolio_retry.get("id") or 0) == int(portfolio["id"]), portfolio_retry
    assert portfolio_retry.get("idempotent_replay") is True, portfolio_retry

    portfolio_updated = call(
        "PATCH",
        f"/api/v1/freelancer/portfolio/{portfolio['id']}",
        {
            "title": "نموذج عمل E2E محدث",
            "description": "تم تحديث الوصف للتأكد أن المستقل يقدر يعدل معرض أعماله بدون حذف السجل.",
            "external_url": "https://example.com/minjaz-e2e-work-updated",
        },
        freelancer_token,
        expected=(200,),
    )
    assert portfolio_updated.get("title") == "نموذج عمل E2E محدث", portfolio_updated
    portfolio_items = call("GET", "/api/v1/freelancer/portfolio", token=freelancer_token, expected=(200,)).get("items") or []
    assert len([x for x in portfolio_items if int(x.get("id") or 0) == int(portfolio["id"])]) == 1, portfolio_items
    assert next(x for x in portfolio_items if int(x.get("id") or 0) == int(portfolio["id"]))["external_url"].endswith("-updated"), portfolio_items

    client_ready = call("GET", "/api/v1/onboarding", token=client_token, expected=(200,))
    freelancer_ready = call("GET", "/api/v1/onboarding", token=freelancer_token, expected=(200,))
    assert client_ready.get("complete") is True, client_ready
    assert next(x for x in client_ready["steps"] if x.get("key") == "profile").get("done") is True, client_ready
    assert next(x for x in client_ready["steps"] if x.get("key") == "first_task").get("done") is True, client_ready
    assert int(client_ready.get("completion_percent") or 0) == 100, client_ready
    assert freelancer_ready.get("complete") is True, freelancer_ready
    assert next(x for x in freelancer_ready["steps"] if x.get("key") == "portfolio").get("done") is True, freelancer_ready
    assert int(freelancer_ready.get("completion_percent") or 0) == 100, freelancer_ready

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

    client_after_task = call("GET", "/api/v1/onboarding", token=client_token, expected=(200,))
    first_task_step = next(x for x in client_after_task["steps"] if x.get("key") == "first_task")
    assert first_task_step.get("done") is True, client_after_task
    assert int(client_after_task.get("completion_percent") or 0) == 100, client_after_task

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

    proposal_history_sent = call(
        "GET",
        "/api/v1/freelancer/proposals",
        token=freelancer_token,
        expected=(200,),
    ).get("items") or []
    history_sent = next((x for x in proposal_history_sent if int(x.get("id") or 0) == int(proposal_id)), None)
    assert history_sent, proposal_history_sent
    assert history_sent.get("proposal_status") == "sent", history_sent
    assert int(history_sent.get("task_id") or 0) == int(task_id), history_sent
    assert history_sent.get("order_id") is None, history_sent

    # Concurrent retries of the same invite must resolve to one logical invitation and one notification.
    invite_payload = {"task_id": task_id, "note": "دعوة اختبار للمستقل قبل اعتماد العرض."}
    invite_barrier = Barrier(2)
    def invite_same(_):
        invite_barrier.wait()
        return call(
            "POST",
            f"/api/v1/freelancers/{freelancer_me['user']['id']}/invite",
            invite_payload,
            client_token,
            expected=(200, 201),
        )
    with ThreadPoolExecutor(max_workers=2) as ex:
        invite_results = list(ex.map(invite_same, (1, 2)))
    assert len({int(x["id"]) for x in invite_results}) == 1, invite_results
    assert sum(1 for x in invite_results if x.get("idempotent_replay")) == 1, invite_results
    assert all(int(x["task_id"]) == int(task_id) for x in invite_results), invite_results
    invite_notifications = call(
        "GET",
        "/api/v1/notifications?kind=task_invite&unread=1",
        token=freelancer_token,
        expected=(200,),
    )
    task_invite_notes = [
        item for item in (invite_notifications.get("items") or [])
        if int(item.get("task_id") or 0) == int(task_id)
    ]
    assert len(task_invite_notes) == 1, task_invite_notes

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

    proposal_history_selected = call(
        "GET",
        "/api/v1/freelancer/proposals",
        token=freelancer_token,
        expected=(200,),
    ).get("items") or []
    history_selected = next((x for x in proposal_history_selected if int(x.get("id") or 0) == int(proposal_id)), None)
    assert history_selected, proposal_history_selected
    assert history_selected.get("proposal_status") == "accepted", history_selected
    assert int(history_selected.get("order_id") or 0) == int(order_id), history_selected
    assert history_selected.get("order_status") == "awaiting_payment", history_selected
    assert history_selected.get("payment_status") == "unpaid", history_selected

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

    proposal_history_completed = call(
        "GET",
        "/api/v1/freelancer/proposals",
        token=freelancer_token,
        expected=(200,),
    ).get("items") or []
    history_completed = next((x for x in proposal_history_completed if int(x.get("id") or 0) == int(proposal_id)), None)
    assert history_completed and history_completed.get("proposal_status") == "accepted", history_completed
    assert history_completed.get("order_status") == "completed", history_completed
    assert history_completed.get("payment_status") == "paid", history_completed

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
        "account_updates_retry_safe": True,
        "session_revocation_retry_safe": True,
        "onboarding_client": True,
        "onboarding_freelancer": True,
        "legal_acceptance": True,
        "legal_precondition_enforced": True,
        "freelancer_profile_readiness": True,
        "client_profile_readiness": True,
        "portfolio_readiness": True,
        "onboarding_completion_100": True,
        "tasks": True,
        "proposals": True,
        "freelancer_proposal_history": True,
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
        "task_invite_retry_safe": True,
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
