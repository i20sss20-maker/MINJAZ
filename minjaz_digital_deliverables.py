"""Private delivery-link API for sandbox digital-service orders.

This module stores HTTPS pointers; it never fetches third-party URLs or uploads bytes.
New links are admin-only, tied to an order, and hidden from the customer until the
workflow atomically transitions the order to "delivered".
"""
import ipaddress
import re
from urllib.parse import urlsplit

from minjaz_digital_workflow import _preview

HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _safe_https_url(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 2000:
        return False
    if any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or not host or not HOST_RE.fullmatch(host)
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        if host.endswith((".local", ".localhost", ".internal", ".invalid", ".test")):
            return False
        return True
    except ValueError:
        return False


def dispatch(method, path, query, body, actor, connect):
    prefix = "/api/digital-services/"
    if not path.startswith(prefix):
        return 404, {"error": "not_found"}
    bits = path[len(prefix):].strip("/").split("/")
    is_admin = len(bits) == 4 and bits[0:2] == ["admin", "orders"] and bits[-1] == "deliverables"
    is_customer = len(bits) == 3 and bits[0] == "orders" and bits[-1] == "deliverables"
    if not (is_admin or is_customer):
        return 404, {"error": "not_found"}
    if actor is None:
        return 401, {"error": "unauthorized"}
    if is_admin and actor.get("role") != "admin":
        return 403, {"error": "admin_only"}
    suffix = bits[-2]
    if not suffix.isascii() or not suffix.isdigit() or int(suffix) <= 0:
        return 404, {"error": "not_found"}
    order_id = int(suffix)
    actor_id = int(actor["id"])
    if method == "POST" and is_customer:
        return 403, {"error": "admin_only"}
    if method not in (("GET", "POST") if is_admin else ("GET",)):
        return 405, {"error": "method_not_allowed"}

    if method == "POST":
        if not isinstance(body, dict) or set(body) != {"title", "url"}:
            return 400, {"error": "invalid_deliverable"}
        title = body.get("title")
        url = body.get("url")
        if not isinstance(title, str) or not 3 <= len(title.strip()) <= 120:
            return 400, {"error": "invalid_title"}
        if not _safe_https_url(url):
            return 400, {"error": "invalid_delivery_url"}
        if not _preview():
            return 403, {"error": "sandbox_only"}

    c = connect()
    try:
        with c.cursor() as cur:
            if method == "POST":
                c.autocommit = False
                cur.execute("SELECT status FROM digital_service_orders WHERE id=%s FOR UPDATE",(order_id,))
                found = cur.fetchone()
                if not found:
                    return 404, {"error": "order_not_found"}
                if found[0] != "in_progress":
                    return 409, {"error": "order_not_in_progress"}
                cur.execute("SELECT COUNT(*) FROM digital_service_deliverables WHERE order_id=%s",(order_id,))
                if cur.fetchone()[0] >= 25:
                    return 409, {"error": "delivery_link_limit_reached"}
                cur.execute("""INSERT INTO digital_service_deliverables (order_id,admin_id,title,url)
                  VALUES (%s,%s,%s,%s)
                  ON CONFLICT (order_id,url) DO NOTHING RETURNING id""",
                  (order_id,actor_id,title.strip(),url))
                inserted = cur.fetchone()
                if not inserted:
                    return 409, {"error": "duplicate_delivery_url"}
                c.commit()
                return 201, {"id": inserted[0], "order_id": order_id, "published": False}
            if is_admin:
                cur.execute("SELECT 1 FROM digital_service_orders WHERE id=%s",(order_id,))
            else:
                cur.execute("SELECT 1 FROM digital_service_orders WHERE id=%s AND customer_id=%s",
                            (order_id,actor_id))
            if not cur.fetchone():
                return 404, {"error": "order_not_found"}
            if is_admin:
                cur.execute("""SELECT id,title,url,created_at,published_at
                  FROM digital_service_deliverables WHERE order_id=%s
                  ORDER BY id DESC LIMIT 100""",(order_id,))
            else:
                cur.execute("""SELECT id,title,url,created_at,published_at
                  FROM digital_service_deliverables WHERE order_id=%s
                    AND published_at IS NOT NULL ORDER BY id DESC LIMIT 100""",(order_id,))
            assets = [{"id":row[0],"title":row[1],"url":row[2],
                       "created_at":row[3].isoformat(),
                       "published":row[4] is not None,
                       "published_at":row[4].isoformat() if row[4] else None}
                      for row in cur.fetchall()]
            return 200, {"order_id":order_id, "deliverables":assets}
    except Exception:
        if method == "POST":
            c.rollback()
        raise
    finally:
        c.close()
