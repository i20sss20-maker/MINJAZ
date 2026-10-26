"""MINJAZ first-party digital services API. No payment writes or production flags."""
from decimal import Decimal
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
            if type(package_id) is not int or package_id <= 0 or not isinstance(requirements, str) or not 10 <= len(requirements.strip()) <= 10000:
                return 400, {'error':'invalid_order'}
        c=connect(); c.autocommit=False
        try:
            with c.cursor() as cur:
                if method=='GET':
                    cur.execute("""SELECT o.id,p.title_ar,o.agreed_price_sar,o.status,o.created_at
                      FROM digital_service_orders o JOIN digital_service_packages p ON p.id=o.package_id
                      WHERE o.customer_id=%s ORDER BY o.id DESC LIMIT 100""",(user_id,))
                    return 200, {'orders':[{'id':r[0],'title_ar':r[1],'price_sar':str(r[2]),
                      'status':r[3],'created_at':r[4].isoformat()} for r in cur.fetchall()]}
                cur.execute("""SELECT price_sar,revision_limit FROM digital_service_packages
                  WHERE id=%s AND active=TRUE FOR SHARE""",(package_id,))
                package=cur.fetchone()
                if not package:return 404, {'error':'package_unavailable'}
                cur.execute("""INSERT INTO digital_service_orders
                  (package_id,customer_id,requirements,agreed_price_sar,agreed_revision_limit)
                  VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                  (package_id,user_id,requirements.strip(),package[0],package[1]))
                oid=cur.fetchone()[0]
            c.commit()
            return 201, {'order_id':oid,'status':'draft'}
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
                cur.execute("""SELECT o.id,p.title_ar,o.agreed_price_sar,o.status,o.created_at,o.requirements
                  FROM digital_service_orders o JOIN digital_service_packages p ON p.id=o.package_id
                  WHERE o.id=%s AND o.customer_id=%s""",(int(suffix),int(actor['id'])))
                r=cur.fetchone()
                if not r:return 404, {'error':'order_not_found'}
                return 200, {'order':{'id':r[0],'title_ar':r[1],'price_sar':str(r[2]),
                  'status':r[3],'created_at':r[4].isoformat(),'requirements':r[5]}}
        finally:c.close()
    return 405, {'error':'method_not_allowed'}
