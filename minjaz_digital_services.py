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
        if category and category not in ('website','mobile_app','ecommerce','branding','maintenance','ai','marketing','seo','content','video','automation','data','security','consulting'):
            return 400, {'error':'invalid_category'}
        c=connect()
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT id,slug,category,title_ar,description_ar,price_sar,delivery_days,revision_limit
                  FROM digital_service_packages WHERE active=TRUE AND (%s IS NULL OR category=%s)
                  ORDER BY id DESC LIMIT 100""",(category,category))
                return 200, {'services':[_public_package(row) for row in cur.fetchall()]}
        finally: c.close()
    if path == '/api/digital-services/activity' and method == 'GET':
        if not actor:return 401, {'error':'unauthorized'}
        customer_id=int(actor['id'])
        c=connect()
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT ev.id,ev.order_id,p.title_ar,ev.new_status,ev.created_at
                  FROM digital_service_order_events ev
                  JOIN digital_service_orders o ON o.id=ev.order_id
                  JOIN digital_service_packages p ON p.id=o.package_id
                  WHERE o.customer_id=%s AND ev.actor_id<>o.customer_id
                  ORDER BY ev.id DESC LIMIT 30""",(customer_id,))
                return 200, {'activity':[{'event_id':row[0],'order_id':row[1],
                    'title_ar':row[2],'status':row[3],'created_at':row[4].isoformat()}
                    for row in cur.fetchall()]}
        finally:c.close()
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
            # Never accept preview draft orders if this module is accidentally
            # deployed outside the dedicated sandbox project.
            from minjaz_digital_workflow import _preview
            if not _preview():
                return 403, {'error':'sandbox_only'}
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
                cur.execute("""INSERT INTO digital_service_order_events
                  (order_id,actor_id,previous_status,new_status,note)
                  VALUES (%s,%s,%s,%s,%s)""",
                  (oid,user_id,'created','draft',None))
            c.commit()
            return 201, {'order_id':oid,'status':'draft','idempotent_replay':False}
        except Exception:
            c.rollback();raise
        finally:c.close()
    if path.startswith('/api/digital-services/orders/') and method=='PATCH':
        if not actor:return 401, {'error':'unauthorized'}
        suffix=path.rsplit('/',1)[-1]
        if not suffix.isascii() or not suffix.isdigit() or int(suffix)<=0:
            return 404, {'error':'not_found'}
        if not isinstance(body,dict) or set(body) != {'requirements'}:
            return 400, {'error':'invalid_payload'}
        requirements=body['requirements']
        if not isinstance(requirements,str) or not 10<=len(requirements.strip())<=10000:
            return 400, {'error':'invalid_requirements'}
        from minjaz_digital_workflow import _preview
        if not _preview():
            return 403, {'error':'sandbox_only'}
        order_id=int(suffix);customer_id=int(actor['id'])
        c=connect();c.autocommit=False
        try:
            with c.cursor() as cur:
                cur.execute("""SELECT status FROM digital_service_orders
                  WHERE id=%s AND customer_id=%s FOR UPDATE""",(order_id,customer_id))
                row=cur.fetchone()
                if not row:
                    return 404, {'error':'order_not_found'}
                if row[0]!='draft':
                    return 409, {'error':'order_not_editable','status':row[0]}
                cur.execute("""UPDATE digital_service_orders SET requirements=%s,updated_at=NOW()
                  WHERE id=%s AND customer_id=%s""",(requirements.strip(),order_id,customer_id))
                cur.execute("""INSERT INTO digital_service_order_events
                  (order_id,actor_id,previous_status,new_status,note)
                  VALUES (%s,%s,%s,%s,%s)""",
                  (order_id,customer_id,'draft','draft','تم تعديل متطلبات الطلب'))
            c.commit()
            return 200, {'order_id':order_id,'status':'draft','requirements':requirements.strip()}
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
                cur.execute("""SELECT note,created_at FROM digital_service_revisions
                  WHERE order_id=%s AND customer_id=%s ORDER BY id DESC LIMIT 100""",
                  (int(suffix),int(actor['id'])))
                revision_rows=cur.fetchall()
                revisions=[{'note':note,'created_at':created.isoformat()} for note,created in revision_rows]
                cur.execute("""SELECT previous_status,new_status,note,created_at
                  FROM digital_service_order_events WHERE order_id=%s ORDER BY id DESC LIMIT 100""",
                  (int(suffix),))
                events=[{'previous_status':before,'new_status':after,'note':note,
                         'created_at':created.isoformat()} for before,after,note,created in cur.fetchall()]
                return 200, {'order':{'id':r[0],'title_ar':r[1],'price_sar':str(r[2]),
                  'status':r[3],'created_at':r[4].isoformat(),'requirements':r[5],
                  'delivery_note':r[6],'revision_limit':r[7],'revisions_used':len(revisions),
                  'events':events,'revisions':revisions}}
        finally:c.close()
    return 405, {'error':'method_not_allowed'}
