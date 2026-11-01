"""Structured marketplace specialties for verified freelancer accounts.

No KYC claims, no payment operations. Only marketplace specializations (market-*)
are eligible. The PATCH operation replaces the authenticated account's selection
atomically; concurrent requests serialize on the freelancer profile row.
"""
MAX_SPECIALTIES=12
MAX_BIGINT=9223372036854775807

def validate_selection(body):
    if not isinstance(body,dict) or set(body)!={'service_ids'}:
        return None,'invalid_specialty_payload'
    values=body['service_ids']
    if not isinstance(values,list) or len(values)>MAX_SPECIALTIES:
        return None,'invalid_specialty_count'
    if any(type(x) is not int or not 0<x<=MAX_BIGINT for x in values):
        return None,'invalid_specialty_id'
    if len(values)!=len(set(values)):
        return None,'duplicate_specialty'
    return values,None

def dispatch(method,path,body,actor,connect):
    if path!='/api/v1/freelancer/specialties':
        return 404,{'error':'not_found'}
    if not actor:return 401,{'error':'unauthorized'}
    if actor.get('role')!='freelancer':return 403,{'error':'freelancer_only'}
    if method not in ('GET','PATCH'):return 405,{'error':'method_not_allowed'}
    ids=None
    if method=='PATCH':
        ids,error=validate_selection(body)
        if error:return 400,{'error':error}
    db=connect()
    try:
        db.autocommit=False
        with db.cursor() as cur:
            if method=='PATCH':
                cur.execute("SELECT user_id FROM freelancer_profiles WHERE user_id=%s FOR UPDATE",
                            (actor['id'],))
                if not cur.fetchone():
                    return 404,{'error':'freelancer_profile_not_found'}
                if ids:
                    cur.execute("""SELECT s.id FROM services s JOIN categories c
                        ON c.id=s.category_id
                        WHERE s.id=ANY(%s) AND s.active=TRUE AND c.is_active=TRUE
                        AND s.slug LIKE 'market-%%'""",(ids,))
                    allowed={int(row[0]) for row in cur.fetchall()}
                    if allowed!=set(ids):
                        return 400,{'error':'inactive_or_invalid_specialty'}
                cur.execute("DELETE FROM freelancer_marketplace_specialties WHERE user_id=%s",
                            (actor['id'],))
                if ids:
                    cur.executemany("""INSERT INTO freelancer_marketplace_specialties
                        (user_id,service_id) VALUES (%s,%s)""",
                        [(actor['id'],service_id) for service_id in ids])
            cur.execute("""SELECT s.id,s.category_id,s.name_ar,c.name_ar
                FROM freelancer_marketplace_specialties fs
                JOIN services s ON s.id=fs.service_id
                JOIN categories c ON c.id=s.category_id
                WHERE fs.user_id=%s ORDER BY fs.created_at,fs.service_id
                LIMIT %s""",(actor['id'],MAX_SPECIALTIES))
            items=[{'service_id':row[0],'category_id':row[1],'name_ar':row[2],
                    'category_name':row[3]} for row in cur.fetchall()]
        if method=='PATCH':db.commit()
        else:db.rollback()
        return 200,{'items':items,'max_specialties':MAX_SPECIALTIES}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
