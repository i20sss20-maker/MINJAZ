"""MINJAZ first-party digital services API. No payment writes or production flags."""
from decimal import Decimal
import hashlib
import json
import re
import psycopg2

def _public_package(row):
    return {'id':row[0], 'slug':row[1], 'category':row[2], 'title_ar':row[3],
            'description_ar':row[4], 'price_sar':str(row[5]),
            'delivery_days':row[6], 'revision_limit':row[7]}

def dispatch(method, path, query, body, actor, connect):
    """Return (status, payload); caller authenticates using MINJAZ auth(headers)."""
    if path == '/api/digital-services/catalog' and method == 'GET':
        category=(query.get('category') or [None])[0]
        if category and category not in ('website','mobile_app','ecommerce','branding','maintenance','ai'):
            return 400, {'error':'invalid_category'}
        c=connect()
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT id,slug,category,title_ar,description_ar,price_sar,delivery_days,revision_limit
                  FROM digital_service_packages WHERE active=TRUE AND (%s IS NULL OR category=%s)
                  ORDER BY id DESC LIMIT 100""",(category,category))
                return 200, {'services':[_public_package(row) for row in cur.fetchall()]}
        finally: c.close()
    if path == '/api/digital-services/orders' and method in ('GET','POST'):
        if not actor:return 401, {'error':'unauthorized'}
        user_id=int(actor['id'])
        if method == 'POST':
            if not isinstance(body, dict):
                return 400, {'error':'invalid_payload'}
            package_id = body.get('package_id')
            requirements = body.get('requirements')
            idempotency_key = body.get('idempotency_key')
            if type(package_id) is not int or package_id <= 0 or not isinstance(requirements, str) or not 10 <= len(requirements.strip()) <= 10000:
                return 400, {'error':'invalid_order'}
            if idempotency_key is not None and (not isinstance(idempotency_key,str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key)):
                return 400, {'error':'invalid_idempotency_key'}
            fingerprint = hashlib.sha256(json.dumps(
                [package_id,requirements.strip()],ensure_ascii=False,separators=(',',':')
            ).encode('utf-8')).hexdigest()
        c=connect(); c.autocommit=False
        try:
            with c.cursor() as cur:
                if method=='GET':
                    cur.execute("""SELECT o.id,p.title_ar,o.agreed_price_sar,o.status,o.created_at
                      FROM digital_service_orders o JOIN digital_service_packages p ON p.id=o.package_id
                      WHERE o.customer_id=%s ORDER BY o.id DESC LIMIT 100""",(user_id,))
                    return 200, {'orders':[{'id':r[0],'title_ar':r[1],'price_sar':str(r[2]),
                      'status':r[3],'created_at':r[4].isoformat()} for r in cur.fetchall()]}
                if idempotency_key is not None:
                    cur.execute("""SELECT id,request_fingerprint,status
                      FROM digital_service_orders WHERE customer_id=%s AND request_idempotency_key=%s""",
                      (user_id,idempotency_key))
                    earlier=cur.fetchone()
                    if earlier:
                        if earlier[1] != fingerprint:return 409, {'error':'idempotency_key_reused'}
                        return 200, {'order_id':earlier[0],'status':earlier[2],'idempotent_replay':True}
                cur.execute("""SELECT price_sar,revision_limit FROM digital_service_packages
                  WHERE id=%s AND active=TRUE FOR SHARE""",(package_id,))
                package=cur.fetchone()
                if not package:return 404, {'error':'package_unavailable'}
                cur.execute("""INSERT INTO digital_service_orders
                  (package_id,customer_id,requirements,agreed_price_sar,agreed_revision_limit,
                   request_idempotency_key,request_fingerprint)
                  VALUES (%s,%s,%s,%s,%s,%s,%s)
                  ON CONFLICT (customer_id,request_idempotency_key)
                    WHERE request_idempotency_key IS NOT NULL DO NOTHING RETURNING id""",
                  (package_id,user_id,requirements.strip(),package[0],package[1],idempotency_key,fingerprint))
                inserted=cur.fetchone()
                if not inserted:
                    if idempotency_key is None:raise RuntimeError('order_insert_not_returned')
                    cur.execute("""SELECT id,request_fingerprint,status
                      FROM digital_service_orders WHERE customer_id=%s AND request_idempotency_key=%s""",
                      (user_id,idempotency_key))
                    prior=cur.fetchone()
                    if prior and prior[1] == fingerprint:
                        return 200, {'order_id':prior[0],'status':prior[2],'idempotent_replay':True}
                    return 409, {'error':'idempotency_key_reused'}
                oid=inserted[0]
            c.commit()
            return 201, {'order_id':oid,'status':'draft','idempotent_replay':False}
        except Exception:
            c.rollback();raise
        finally:c.close()
    if path.startswith('/api/digital-services/orders/') and method=='GET':
        if not actor:return 401, {'error':'unauthorized'}
        suffix=path.rsplit('/',1)[-1]
        if not suffix.isascii() or not suffix.isdigit() or int(suffix)<=0:return 404, {'error':'not_found'}
        c=connect()
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT o.id,p.title_ar,o.agreed_price_sar,o.status,o.created_at,o.requirements,o.delivery_note,o.agreed_revision_limit
                  FROM digital_service_orders o JOIN digital_service_packages p ON p.id=o.package_id
                  WHERE o.id=%s AND o.customer_id=%s""",(int(suffix),int(actor['id'])))
                r=cur.fetchone()
                if not r:return 404, {'error':'order_not_found'}
                cur.execute("SELECT COUNT(*) FROM digital_service_revisions WHERE order_id=%s",(int(suffix),))
                revision_used=cur.fetchone()[0]
                return 200, {'order':{'id':r[0],'title_ar':r[1],'price_sar':str(r[2]),
                  'status':r[3],'created_at':r[4].isoformat(),'requirements':r[5],
                  'delivery_note':r[6],'revision_limit':r[7],'revisions_used':revision_used}}
        finally:c.close()
    return 405, {'error':'method_not_allowed'}
