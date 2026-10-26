"""Isolated preview-only workflow for MINJAZ digital services.

All status changes are audited and performed under a row lock.
No payment, billing, or financial status can be set by this module.
"""
import os

SANDBOX_PROJECT_ID = "b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4"
STATUSES = {"draft", "in_progress", "delivered", "revision_requested", "completed", "cancelled"}
ADMIN_NEXT = {"draft": {"in_progress", "cancelled"},
              "in_progress": {"delivered"},
              "revision_requested": {"in_progress"}}

def _preview():
    return (os.environ.get("APP_ENV") == "preview"
            and os.environ.get("RAILWAY_PROJECT_ID") == SANDBOX_PROJECT_ID
            and os.environ.get("PAYMENT_MODE") == "mock")

def _positive_id(s):
    return int(s) if isinstance(s, str) and s.isascii() and s.isdigit() and int(s) > 0 else None

def _order_info(row):
    return {"id": row[0], "title_ar": row[1], "customer_id": row[2],
            "price_sar": str(row[3]), "status": row[4],
            "requirements": row[5], "delivery_note": row[6],
            "revision_limit": row[7], "created_at": row[8].isoformat()}

def dispatch(method, path, query, body, actor, connect):
    prefix = "/api/digital-services/"
    if not path.startswith(prefix):
        return 404, {"error": "not_found"}
    bits = path[len(prefix):].strip("/").split("/")
    admin_route = bits[0] == "admin"
    if not actor:
        return 401, {"error": "unauthorized"}
    if admin_route and actor.get("role") != "admin":
        return 403, {"error": "admin_only"}

    if admin_route:
        if bits == ["admin", "orders"] and method == "GET":
            requested = (query.get("status") or [None])[0]
            if requested and requested not in STATUSES:
                return 400, {"error": "invalid_status"}
            c = connect()
            try:
                with c.cursor() as cur:
                    cur.execute("""SELECT o.id,p.title_ar,o.customer_id,o.agreed_price_sar,o.status,o.created_at
                      FROM digital_service_orders o
                      JOIN digital_service_packages p ON p.id=o.package_id
                      WHERE (%s IS NULL OR o.status=%s)
                      ORDER BY o.id DESC LIMIT 100""", (requested, requested))
                    return 200, {"orders": [{"id":r[0],"title_ar":r[1],"customer_id":r[2],
                      "price_sar":str(r[3]),"status":r[4],"created_at":r[5].isoformat()} for r in cur.fetchall()]}
            finally:
                c.close()
        if len(bits) != 3 or bits[:2] != ["admin", "orders"]:
            return 404, {"error": "not_found"}
        order_id = _positive_id(bits[2])
        if not order_id:
            return 404, {"error": "not_found"}
        if method == "GET":
            c = connect()
            try:
                with c.cursor() as cur:
                    cur.execute("""SELECT o.id,p.title_ar,o.customer_id,o.agreed_price_sar,o.status,
                      o.requirements,o.delivery_note,o.agreed_revision_limit,o.created_at
                      FROM digital_service_orders o JOIN digital_service_packages p ON p.id=o.package_id
                      WHERE o.id=%s""",(order_id,))
                    row = cur.fetchone()
                    if not row:
                        return 404, {"error": "order_not_found"}
                    cur.execute("""SELECT previous_status,new_status,note,created_at FROM digital_service_order_events
                      WHERE order_id=%s ORDER BY id DESC LIMIT 100""",(order_id,))
                    events = [{"previous_status":r[0],"new_status":r[1],"note":r[2],
                               "created_at":r[3].isoformat()} for r in cur.fetchall()]
                    cur.execute("""SELECT note,created_at FROM digital_service_revisions
                      WHERE order_id=%s ORDER BY id DESC LIMIT 100""",(order_id,))
                    revisions = [{"note":r[0],"created_at":r[1].isoformat()} for r in cur.fetchall()]
                    return 200, {"order": _order_info(row), "events":events, "revisions":revisions}
            finally:
                c.close()
        if method != "PATCH":
            return 405, {"error":"method_not_allowed"}
        if not isinstance(body, dict) or not isinstance(body.get("status"), str):
            return 400, {"error":"invalid_status"}
        target = body["status"]
        note = body.get("note","")
        if not isinstance(note,str) or len(note.strip()) > 3000:
            return 400, {"error":"invalid_note"}
        if target not in {"in_progress","delivered","cancelled"}:
            return 400, {"error":"invalid_status"}
        if target == "delivered" and not 10 <= len(note.strip()) <= 3000:
            return 400, {"error":"delivery_note_required"}
        return _transition(connect,order_id,int(actor["id"]),target,note.strip(),is_admin=True)

    if len(bits) != 3 or bits[0] != "orders":
        return 404, {"error":"not_found"}
    order_id = _positive_id(bits[1])
    if not order_id:
        return 404, {"error":"not_found"}
    action = bits[2]
    if method != "POST" or action not in ("revisions","complete","cancel"):
        return 405, {"error":"method_not_allowed"}
    if action == "revisions":
        if not isinstance(body,dict) or not isinstance(body.get("note"),str) or not 10 <= len(body["note"].strip()) <= 3000:
            return 400, {"error":"invalid_revision_note"}
        return _transition(connect,order_id,int(actor["id"]),"revision_requested",body["note"].strip(),is_admin=False)
    if body is not None and not isinstance(body,dict):
        return 400, {"error":"invalid_payload"}
    target = "completed" if action == "complete" else "cancelled"
    return _transition(connect,order_id,int(actor["id"]),target,"",is_admin=False)

def _transition(connect,order_id,actor_id,target,note,is_admin):
    if not _preview():
        return 403, {"error":"sandbox_only"}
    c = connect()
    c.autocommit = False
    try:
        with c.cursor() as cur:
            cur.execute("""SELECT status,customer_id,agreed_revision_limit
              FROM digital_service_orders WHERE id=%s FOR UPDATE""",(order_id,))
            row = cur.fetchone()
            if row is None or (not is_admin and row[1] != actor_id):
                return 404, {"error":"order_not_found"}
            old = row[0]
            if is_admin:
                allowed = target in ADMIN_NEXT.get(old,set())
            else:
                allowed = ((old == "delivered" and target in ("completed","revision_requested"))
                           or (old == "draft" and target == "cancelled"))
            if not allowed:
                return 409, {"error":"invalid_status_transition","current_status":old}
            if target == "revision_requested":
                cur.execute("SELECT COUNT(*) FROM digital_service_revisions WHERE order_id=%s",(order_id,))
                used = cur.fetchone()[0]
                if used >= row[2]:
                    return 409, {"error":"revision_limit_reached"}
                cur.execute("""INSERT INTO digital_service_revisions(order_id,customer_id,note)
                  VALUES (%s,%s,%s)""",(order_id,actor_id,note))
            if target == "delivered":
                cur.execute("""UPDATE digital_service_orders SET status=%s,delivery_note=%s,updated_at=NOW()
                  WHERE id=%s""",(target,note,order_id))
            else:
                cur.execute("""UPDATE digital_service_orders SET status=%s,updated_at=NOW()
                  WHERE id=%s""",(target,order_id))
            cur.execute("""INSERT INTO digital_service_order_events
              (order_id,actor_id,previous_status,new_status,note)
              VALUES (%s,%s,%s,%s,%s)""",(order_id,actor_id,old,target,note or None))
        c.commit()
        return 200, {"order_id":order_id,"status":target}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
