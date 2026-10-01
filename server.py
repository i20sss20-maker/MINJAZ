import os, json, hashlib, secrets, uuid, re, hmac
import urllib.request, urllib.error
from decimal import Decimal
from datetime import datetime, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from storage import RailwayBucketStorage, StorageError, ALLOWED_TYPES
import psycopg2
import psycopg2.extras

PORT=int(os.getenv('PORT','3000'))
SECRET=os.getenv('AUTH_SECRET','dev-secret-change-me')
DEV_OTP=os.getenv('DEV_OTP','1234')
FEE=Decimal(os.getenv('PLATFORM_FEE_PERCENT','15'))
ADMIN_PHONE=os.getenv('ADMIN_PHONE','').strip()
PAYMENT_MODE=os.getenv('PAYMENT_MODE','mock')
DB_PERSISTENCE=os.getenv('DB_PERSISTENCE','volume_missing')
SMS_MODE=os.getenv('SMS_MODE','dev')
STORAGE_MODE=os.getenv('STORAGE_MODE','postgres_dev')
BUCKET_STORAGE=RailwayBucketStorage()
BUCKET_READY=BUCKET_STORAGE.ready
KYC_MODE=os.getenv('KYC_MODE','manual')
SOURCE_CONTROL=os.getenv('SOURCE_CONTROL','railway_env')
VERSION=os.getenv('MINJAZ_VERSION','0.5.5-rc5')
APP_ENV=os.getenv('APP_ENV','beta').strip().lower()
SESSION_TTL_DAYS=max(1,min(int(os.getenv('SESSION_TTL_DAYS','30')),365))
LEGAL_TERMS_VERSION=os.getenv('LEGAL_TERMS_VERSION','2026-09-beta1')
LEGAL_PRIVACY_VERSION=os.getenv('LEGAL_PRIVACY_VERSION','2026-09-beta1')
LEGAL_MARKETPLACE_VERSION=os.getenv('LEGAL_MARKETPLACE_VERSION','2026-09-beta1')
LEGAL_REVIEW_STATUS=os.getenv('LEGAL_REVIEW_STATUS','draft').strip().lower()
LAUNCH_GUARD=os.getenv('COMMERCIAL_LAUNCH_GUARD','0').strip()=='1'
RUN_RUNTIME_SCHEMA_ENSURE=os.getenv('RUN_RUNTIME_SCHEMA_ENSURE','0').strip()=='1'
IS_PROD=APP_ENV=='production'
PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
SMS_WEBHOOK_URL=os.getenv('SMS_WEBHOOK_URL','').strip()
SMS_WEBHOOK_BEARER=os.getenv('SMS_WEBHOOK_BEARER','').strip()
PAYMENT_CREATE_URL=os.getenv('PAYMENT_CREATE_URL','').strip()
PAYMENT_ADAPTER_BEARER=os.getenv('PAYMENT_ADAPTER_BEARER','').strip()
PAYMENT_WEBHOOK_SECRET=os.getenv('PAYMENT_WEBHOOK_SECRET','').strip()
KYC_START_URL=os.getenv('KYC_START_URL','').strip()
KYC_ADAPTER_BEARER=os.getenv('KYC_ADAPTER_BEARER','').strip()
KYC_WEBHOOK_SECRET=os.getenv('KYC_WEBHOOK_SECRET','').strip()
_cors_raw=os.getenv('CORS_ORIGINS',os.getenv('CORS_ORIGIN','https://minjaz-unified-production.up.railway.app'))
CORS_ORIGINS={x.strip().rstrip('/') for x in _cors_raw.split(',') if x.strip()}

def _https_url(v):
    try:
        u=urlparse(str(v or ''))
        return u.scheme=='https' and bool(u.netloc)
    except Exception:
        return False

def production_blockers():
    blockers=[]
    if SECRET=='dev-secret-change-me' or len(SECRET)<32: blockers.append('AUTH_SECRET')
    if SMS_MODE!='adapter' or not _https_url(SMS_WEBHOOK_URL) or len(SMS_WEBHOOK_BEARER)<16: blockers.append('SMS_ADAPTER')
    if PAYMENT_MODE!='adapter' or not _https_url(PAYMENT_CREATE_URL) or len(PAYMENT_ADAPTER_BEARER)<16 or len(PAYMENT_WEBHOOK_SECRET)<32: blockers.append('PAYMENT_ADAPTER')
    if STORAGE_MODE!='railway_bucket' or not BUCKET_READY: blockers.append('STORAGE_MODE')
    if KYC_MODE!='adapter' or not _https_url(KYC_START_URL) or len(KYC_ADAPTER_BEARER)<16 or len(KYC_WEBHOOK_SECRET)<32: blockers.append('KYC_ADAPTER')
    if DB_PERSISTENCE!='persistent': blockers.append('DB_PERSISTENCE')
    if SOURCE_CONTROL in ('railway_env','none',''): blockers.append('SOURCE_CONTROL')
    if RUN_RUNTIME_SCHEMA_ENSURE: blockers.append('RUN_RUNTIME_SCHEMA_ENSURE')
    if LEGAL_REVIEW_STATUS!='approved': blockers.append('LEGAL_REVIEW')
    if not PUBLIC_BASE_URL or not _https_url(PUBLIC_BASE_URL): blockers.append('PUBLIC_BASE_URL')
    if not CORS_ORIGINS or '*' in CORS_ORIGINS or any(not _https_url(x) for x in CORS_ORIGINS): blockers.append('CORS_ORIGINS')
    return blockers

if IS_PROD:
    _prod_blockers=production_blockers()
    if _prod_blockers:
        raise RuntimeError('Production safety guard blocked startup: '+','.join(_prod_blockers))
HTML_PATH=os.getenv('HTML_PATH',os.path.join(os.path.dirname(__file__),'public','index.html'))
_storage_ep=urlparse(BUCKET_STORAGE.endpoint) if BUCKET_STORAGE.endpoint else None
STORAGE_CSP_CONNECT=(f" {_storage_ep.scheme}://*.{_storage_ep.netloc}" if _storage_ep and _storage_ep.scheme in ('http','https') and _storage_ep.netloc and BUCKET_STORAGE.url_style=='virtual' else (f" {_storage_ep.scheme}://{_storage_ep.netloc}" if _storage_ep and _storage_ep.scheme in ('http','https') and _storage_ep.netloc else ''))

DATABASE_URL=os.getenv('DATABASE_URL','').strip()
DB=dict(host=os.getenv('PGHOST'),port=int(os.getenv('PGPORT','5432')),user=os.getenv('PGUSER'),password=os.getenv('PGPASSWORD'),dbname=os.getenv('PGDATABASE'))
MISSING_DB_ENV=[] if DATABASE_URL else [k for k,v in [('PGHOST',DB['host']),('PGUSER',DB['user']),('PGPASSWORD',DB['password']),('PGDATABASE',DB['dbname'])] if not v]
if MISSING_DB_ENV:
    raise RuntimeError('Missing database configuration: set DATABASE_URL or '+','.join(MISSING_DB_ENV))

def db_connect():
    return psycopg2.connect(DATABASE_URL) if DATABASE_URL else psycopg2.connect(**DB)

def conn():
    c=db_connect()
    c.autocommit=True
    return c

def sha(s): return hashlib.sha256(str(s).encode()).hexdigest()
def normalize_phone(value):
    raw=str(value or '').strip()
    digits=re.sub(r'\D','',raw)
    if digits.startswith('00966'): digits=digits[2:]
    if digits.startswith('966') and len(digits)==12 and digits[3]=='5': return '+'+digits
    if digits.startswith('05') and len(digits)==10: return '+966'+digits[1:]
    if digits.startswith('5') and len(digits)==9: return '+966'+digits
    if raw.startswith('+') and len(digits)>=9: return '+'+digits
    return ''
def as_json(v):
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, (datetime,date)): return v.isoformat()
    return v

def adapter_post_json(url,payload,bearer='',timeout=8):
    if not _https_url(url):
        raise RuntimeError('adapter_url_invalid')
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':f'MINJAZ/{VERSION}'}
    if bearer: headers['Authorization']='Bearer '+bearer
    req=urllib.request.Request(url,data=data,headers=headers,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            raw=resp.read(262144)
            if resp.status<200 or resp.status>=300:
                raise RuntimeError('adapter_http_'+str(resp.status))
            return json.loads(raw or b'{}')
    except urllib.error.HTTPError as exc:
        raise RuntimeError('adapter_http_'+str(exc.code)) from exc
    except (urllib.error.URLError,TimeoutError,ValueError) as exc:
        raise RuntimeError('adapter_unavailable') from exc

def rate_limit_event(kind,key,limit,window_seconds):
    key_hash=sha(str(key)+':'+SECRET)
    c=db_connect(); c.autocommit=False
    try:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Serialize each rate-limit bucket so concurrent requests cannot all pass the count-before-insert window.
            cur.execute('select pg_advisory_xact_lock(hashtext(%s))',(f'rate:{kind}:{key_hash}',))
            cur.execute("delete from security_rate_events where created_at<now()-interval '2 days'")
            cur.execute("select count(*)::int n from security_rate_events where kind=%s and key_hash=%s and created_at>now()-(%s || ' seconds')::interval",(kind,key_hash,int(window_seconds)))
            row=cur.fetchone() or {'n':0}
            if int(row.get('n') or 0)>=int(limit):
                c.commit(); return False
            cur.execute('insert into security_rate_events(kind,key_hash) values(%s,%s)',(kind,key_hash))
        c.commit(); return True
    except Exception:
        c.rollback(); raise
    finally:
        c.close()

class AdapterEventError(Exception):
    def __init__(self,status,code):
        super().__init__(code); self.status=int(status); self.code=str(code)

def apply_payment_adapter_event(b):
    event_id=str(b.get('event_id') or '').strip()[:180]; event_type=str(b.get('type') or '').strip()[:80]; provider_payment_id=str(b.get('provider_payment_id') or '').strip()[:180]
    try: oid=int(b.get('order_id') or 0)
    except Exception: oid=0
    if not event_id or not oid or not provider_payment_id or event_type not in ('payment.succeeded','payment.failed'): raise AdapterEventError(400,'invalid_payment_event')
    c=db_connect(); c.autocommit=False
    try:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('select pg_advisory_xact_lock(hashtext(%s))',('payment:'+event_id,))
            cur.execute('select * from payment_adapter_events where provider_event_id=%s for update',(event_id,)); ev=cur.fetchone()
            if ev and ev.get('processed_at'):
                c.commit(); return {'duplicate':True,'event_type':event_type,'order':None,'changed':False}
            if ev and (int(ev['order_id'])!=oid or ev['event_type']!=event_type or (ev.get('provider_payment_id') or '')!=(provider_payment_id or '')):
                raise AdapterEventError(409,'payment_event_conflict')
            cur.execute('select * from orders where id=%s for update',(oid,)); o=cur.fetchone()
            if not o: raise AdapterEventError(404,'order_not_found')
            if o.get('provider_payment_id') and provider_payment_id and o.get('provider_payment_id')!=provider_payment_id: raise AdapterEventError(409,'provider_payment_mismatch')
            amount=b.get('amount')
            if amount is not None:
                try:
                    if Decimal(str(amount)).quantize(Decimal('0.01'))!=Decimal(str(o['amount'])).quantize(Decimal('0.01')): raise AdapterEventError(409,'amount_mismatch')
                except AdapterEventError: raise
                except Exception: raise AdapterEventError(400,'invalid_amount')
            if not ev:
                cur.execute('insert into payment_adapter_events(provider_event_id,order_id,event_type,provider_payment_id,payload) values(%s,%s,%s,%s,%s::jsonb)',(event_id,oid,event_type,provider_payment_id or None,json.dumps(b,ensure_ascii=False)))
            changed=False; workflow_started=False; late_cancelled_payment=False; failed_effective=False
            if event_type=='payment.succeeded' and o.get('payment_status')!='paid':
                if o.get('status')=='awaiting_payment':
                    cur.execute("update orders set payment_status='paid',status='in_progress',provider_payment_id=%s,payment_checkout_started_at=null where id=%s",(provider_payment_id,oid))
                    cur.execute("update tasks set status='in_progress',updated_at=now() where id=%s and status='matched'",(o['task_id'],)); changed=True; workflow_started=True
                elif o.get('status')=='cancelled':
                    # A provider can confirm payment after a cancellation raced with checkout. Preserve the cancellation,
                    # record the financial fact, and force refund review instead of restarting work.
                    cur.execute("update orders set payment_status='paid',provider_payment_id=%s,payment_checkout_started_at=null where id=%s",(provider_payment_id,oid))
                    cur.execute("update order_cancellation_requests set refund_status='manual_required',updated_at=now() where order_id=%s and status='approved' and refund_status in ('not_needed','pending')",(oid,))
                    changed=True; late_cancelled_payment=True
                else:
                    # Do not silently move an unexpected workflow state. Record payment for reconciliation only.
                    cur.execute("update orders set payment_status='paid',provider_payment_id=%s,payment_checkout_started_at=null where id=%s",(provider_payment_id,oid))
                    changed=True
            elif event_type=='payment.failed':
                # A late failure after a confirmed success is informational only and must never regress the order.
                failed_effective=o.get('payment_status')!='paid' and o.get('status')=='awaiting_payment'
            cur.execute('update payment_adapter_events set processed_at=now() where provider_event_id=%s',(event_id,))
        c.commit(); return {'duplicate':False,'event_type':event_type,'order':dict(o),'changed':changed,'workflow_started':workflow_started,'late_cancelled_payment':late_cancelled_payment,'failed_effective':failed_effective,'event_id':event_id}
    except Exception:
        c.rollback(); raise
    finally:
        c.close()

def apply_kyc_adapter_event(b):
    event_id=str(b.get('event_id') or '').strip()[:180]; provider_ref=str(b.get('provider_reference') or '').strip()[:180]; status=str(b.get('status') or '').strip()
    try: uid=int(b.get('user_id') or 0)
    except Exception: uid=0
    if not event_id or not uid or not provider_ref or status not in ('pending','approved','rejected'): raise AdapterEventError(400,'invalid_kyc_event')
    c=db_connect(); c.autocommit=False
    try:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('select pg_advisory_xact_lock(hashtext(%s))',('kyc:'+event_id,))
            cur.execute('select * from kyc_adapter_events where provider_event_id=%s for update',(event_id,)); ev=cur.fetchone()
            if ev and ev.get('processed_at'):
                c.commit(); return {'duplicate':True,'status':status,'user_id':uid,'changed':False}
            if ev and (int(ev['user_id'])!=uid or ev['status']!=status or ev['provider_reference']!=provider_ref): raise AdapterEventError(409,'kyc_event_conflict')
            cur.execute('select user_id,kyc_status,kyc_provider_reference from freelancer_profiles where user_id=%s for update',(uid,)); fp=cur.fetchone()
            if not fp: raise AdapterEventError(404,'freelancer_not_found')
            if fp.get('kyc_provider_reference') and fp.get('kyc_provider_reference')!=provider_ref: raise AdapterEventError(409,'kyc_provider_reference_mismatch')
            if not ev:
                cur.execute('insert into kyc_adapter_events(provider_event_id,user_id,status,provider_reference,payload) values(%s,%s,%s,%s,%s::jsonb)',(event_id,uid,status,provider_ref,json.dumps(b,ensure_ascii=False)))
            if fp.get('kyc_status') in ('approved','rejected') and status!=fp.get('kyc_status'):
                raise AdapterEventError(409,'kyc_status_finalized')
            changed=fp.get('kyc_status')!=status
            cur.execute('update freelancer_profiles set kyc_status=%s,kyc_provider_reference=coalesce(kyc_provider_reference,%s),kyc_started_at=null where user_id=%s',(status,provider_ref,uid))
            cur.execute('update kyc_adapter_events set processed_at=now() where provider_event_id=%s',(event_id,))
        c.commit(); return {'duplicate':False,'status':status,'user_id':uid,'changed':changed,'event_id':event_id}
    except Exception:
        c.rollback(); raise
    finally:
        c.close()

def _match_text(v):
    # Lightweight deterministic normalization for opportunity relevance.
    s=str(v or '').strip().lower()
    s=re.sub(r'[^0-9a-zA-Z\u0600-\u06FF+#. ]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def opportunity_relevance(task, skills):
    """Return a transparent relevance score + matched skills (not an AI prediction)."""
    skills=[str(x).strip() for x in (skills or []) if str(x).strip()]
    if not skills:
        return 0, []
    title=_match_text(task.get('title'))
    desc=_match_text(task.get('description'))
    category=_match_text(task.get('category_name'))
    service=_match_text(task.get('service_name'))
    hay=' '.join(x for x in (title,desc,category,service) if x)
    matched=[]
    category_hit=False
    service_hit=False
    for raw in skills:
        sk=_match_text(raw)
        if not sk:
            continue
        if sk in hay:
            matched.append(raw)
        if category and (sk in category or category in sk):
            category_hit=True
        if service and (sk in service or service in sk):
            service_hit=True
    score=25
    if category_hit: score+=25
    if service_hit: score+=10
    score+=min(40,len(matched)*20)
    return min(score,95), matched[:3]

def valid_attachment_url(v):
    try:
        u=urlparse(str(v or '').strip())
        return u.scheme=='https' and bool(u.netloc) and len(str(v))<=2048
    except Exception:
        return False


def clean_attachments(items,limit=5,uploaded_by=None):
    out=[]
    if not isinstance(items,list): return out
    for x in items[:limit]:
        if not isinstance(x,dict): continue
        name=str(x.get('name') or x.get('file_name') or 'ملف').strip()[:180] or 'ملف'
        storage_key=str(x.get('storage_key') or '').strip().lstrip('/')
        if storage_key:
            if uploaded_by is None or not BUCKET_READY or not BUCKET_STORAGE.safe_key_for_user(storage_key,uploaded_by):
                continue
            intent=q("select file_name,mime_type,size_bytes from upload_intents where user_id=%s and object_key=%s and completed_at is not null and consumed_at is null and expires_at>now()-interval '24 hours'",(uploaded_by,storage_key),'one')
            if not intent: continue
            out.append({'name':intent['file_name'],'url':'railway-bucket://'+storage_key,'storage_key':storage_key,'storage_mode':'railway_bucket','mime_type':intent['mime_type'],'size_bytes':int(intent['size_bytes'])})
            continue
        url=str(x.get('url') or x.get('file_url') or '').strip()
        if not valid_attachment_url(url): continue
        mime=str(x.get('mime_type') or 'application/octet-stream').strip()[:120]
        try: size=max(0,min(int(x.get('size_bytes') or 0),10_000_000_000))
        except Exception: size=0
        out.append({'name':name,'url':url,'storage_key':None,'storage_mode':'external_link','mime_type':mime,'size_bytes':size})
    return out


def insert_attachments(uploaded_by,attachments,task_id=None,order_id=None,message_id=None,delivery_id=None):
    for a in clean_attachments(attachments,uploaded_by=uploaded_by):
        if a.get('storage_mode')=='railway_bucket':
            c=db_connect()
            try:
                c.autocommit=False
                with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("select id from upload_intents where user_id=%s and object_key=%s and completed_at is not null and consumed_at is null for update",(uploaded_by,a['storage_key']))
                    if not cur.fetchone():
                        c.rollback(); continue
                    cur.execute("insert into attachments(uploaded_by,task_id,order_id,message_id,delivery_id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'railway_bucket') returning id",(uploaded_by,task_id,order_id,message_id,delivery_id,a['name'],a['url'],a['storage_key'],a['mime_type'],a['size_bytes']))
                    cur.execute("update upload_intents set consumed_at=now() where user_id=%s and object_key=%s",(uploaded_by,a['storage_key']))
                c.commit()
            except Exception:
                c.rollback(); raise
            finally:
                c.close()
        else:
            q("insert into attachments(uploaded_by,task_id,order_id,message_id,delivery_id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode) values(%s,%s,%s,%s,%s,%s,%s,null,%s,%s,'external_link')",(uploaded_by,task_id,order_id,message_id,delivery_id,a['name'],a['url'],a['mime_type'],a['size_bytes']),None)


def public_attachment(item):
    x=dict(item)
    if x.get('storage_mode')=='railway_bucket':
        key=x.get('storage_key') or str(x.get('file_url') or '').removeprefix('railway-bucket://')
        x['file_url']=BUCKET_STORAGE.presign('GET',key,expires=900) if BUCKET_READY and key else None
        x['download_expires_in_seconds']=900 if x.get('file_url') else 0
    x.pop('storage_key',None)
    return x


def public_attachments(items):
    return [public_attachment(x) for x in (items or [])]

def rows(cur): return [{k:as_json(v) for k,v in dict(r).items()} for r in cur.fetchall()]

def one(cur):
    r=cur.fetchone(); return None if r is None else {k:as_json(v) for k,v in dict(r).items()}

def q(sql,params=(),fetch='all'):
    with conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql,params)
            if fetch=='all': return rows(cur)
            if fetch=='one': return one(cur)
            return None

def operational_event(level,area,code,message=None,request_id=None,user_id=None,entity_type=None,entity_id=None,meta=None):
    """Best-effort operational telemetry. Never let observability break the product path."""
    try:
        q("insert into operational_events(request_id,level,area,code,message,user_id,entity_type,entity_id,meta) values(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
          (str(request_id or '')[:80] or None,str(level or 'error')[:16],str(area or 'app')[:80],str(code or 'unknown')[:120],str(message or '')[:500] or None,user_id,str(entity_type or '')[:80] or None,str(entity_id or '')[:120] or None,json.dumps(meta or {},ensure_ascii=False)),None)
    except Exception as exc:
        print('OP_EVENT_ERR',repr(exc),flush=True)

def operational_snapshot():
    try:
        counts=q("""select
          count(*) filter(where created_at>now()-interval '15 minutes')::int events_15m,
          count(*) filter(where level in ('error','critical') and created_at>now()-interval '15 minutes')::int errors_15m,
          count(*) filter(where level in ('error','critical') and created_at>now()-interval '24 hours')::int errors_24h,
          max(created_at) last_event_at
          from operational_events""",(), 'one') or {}
        recent=q("select id,request_id,level,area,code,message,entity_type,entity_id,meta,created_at from operational_events order by created_at desc limit 80")
        return {'counts':counts,'recent':recent}
    except Exception as exc:
        return {'counts':{'events_15m':0,'errors_15m':0,'errors_24h':0,'last_event_at':None},'recent':[],'telemetry_error':str(exc)[:120]}

def ensure_schema():
    q("""create table if not exists order_disputes(
        id bigserial primary key,
        order_id bigint not null references orders(id) on delete cascade,
        opened_by bigint not null references users(id),
        reason text not null,
        details text,
        status text not null default 'open',
        previous_order_status text,
        previous_task_status text,
        resolution_action text,
        resolution_note text,
        resolved_by bigint references users(id),
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        resolved_at timestamptz
    );
    create index if not exists idx_order_disputes_order on order_disputes(order_id,created_at desc);
    create index if not exists idx_order_disputes_status on order_disputes(status,created_at desc);
    create table if not exists attachments(
        id bigserial primary key,
        uploaded_by bigint not null references users(id),
        task_id bigint references tasks(id) on delete cascade,
        order_id bigint references orders(id) on delete cascade,
        message_id bigint references messages(id) on delete cascade,
        delivery_id bigint references deliveries(id) on delete cascade,
        file_name text not null,
        file_url text not null,
        mime_type text not null default 'application/octet-stream',
        size_bytes bigint not null default 0,
        storage_mode text not null default 'external_link',
        created_at timestamptz not null default now(),
        check(task_id is not null or order_id is not null or message_id is not null or delivery_id is not null)
    );
    create index if not exists idx_attachments_task on attachments(task_id,created_at);
    create index if not exists idx_attachments_order on attachments(order_id,created_at);
    create index if not exists idx_attachments_message on attachments(message_id,created_at);
    create index if not exists idx_attachments_delivery on attachments(delivery_id,created_at);
    create table if not exists order_revision_requests(
        id bigserial primary key,
        order_id bigint not null references orders(id) on delete cascade,
        requested_by bigint not null references users(id),
        sequence_no int not null,
        note text not null,
        status text not null default 'open',
        created_at timestamptz not null default now(),
        satisfied_at timestamptz,
        unique(order_id,sequence_no)
    );
    create index if not exists idx_revision_requests_order on order_revision_requests(order_id,created_at);""",(),None)


def ensure_payout_schema():
    q("""create table if not exists payout_requests(
        id bigserial primary key,
        freelancer_id bigint not null references users(id) on delete cascade,
        amount numeric(10,2) not null check(amount>0),
        status text not null default 'pending' check(status in ('pending','processing','paid','rejected','cancelled')),
        note text,
        admin_note text,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(),
        resolved_at timestamptz
    );
    create index if not exists idx_payout_requests_freelancer on payout_requests(freelancer_id,created_at desc);
    create index if not exists idx_payout_requests_status on payout_requests(status,created_at desc);""",(),None)

def freelancer_earnings(fid):
    totals=q("""select
        coalesce(sum(case when status='completed' then amount else 0 end),0) gross_earned,
        coalesce(sum(case when status='completed' then coalesce(platform_fee,0) else 0 end),0) platform_fees,
        coalesce(sum(case when status='completed' then amount-coalesce(platform_fee,0) else 0 end),0) net_earned,
        count(*) filter(where status='completed')::int completed_orders
        from orders where freelancer_id=%s""",(fid,), 'one') or {}
    p=q("""select
        coalesce(sum(case when status='paid' then amount else 0 end),0) paid_out,
        coalesce(sum(case when status in ('pending','processing') then amount else 0 end),0) pending_payouts
        from payout_requests where freelancer_id=%s""",(fid,), 'one') or {}
    net=Decimal(str(totals.get('net_earned') or 0))
    paid=Decimal(str(p.get('paid_out') or 0))
    pending=Decimal(str(p.get('pending_payouts') or 0))
    available=max(Decimal('0'),net-paid-pending)
    return {'gross_earned':float(Decimal(str(totals.get('gross_earned') or 0))),'platform_fees':float(Decimal(str(totals.get('platform_fees') or 0))),'net_earned':float(net),'paid_out':float(paid),'pending_payouts':float(pending),'available_balance':float(available),'completed_orders':int(totals.get('completed_orders') or 0)}

def create_payout_request(fid,raw_amount,note=None):
    try:
        amount=Decimal(str(raw_amount)).quantize(Decimal('0.01'))
    except Exception:
        return None,'invalid_amount',None
    if amount<=0:
        return None,'invalid_amount',None
    c=db_connect()
    try:
        c.autocommit=False
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('select id from users where id=%s for update',(fid,))
            if not cur.fetchone():
                c.rollback();return None,'user_not_found',None
            cur.execute('select kyc_status from freelancer_profiles where user_id=%s',(fid,))
            fp=cur.fetchone()
            if not fp or fp.get('kyc_status')!='approved':
                c.rollback();return None,'kyc_required',None
            cur.execute("""select coalesce(sum(case when status='completed' then amount-coalesce(platform_fee,0) else 0 end),0) net_earned from orders where freelancer_id=%s""",(fid,))
            net=Decimal(str(cur.fetchone()['net_earned'] or 0))
            cur.execute("""select coalesce(sum(case when status='paid' then amount else 0 end),0) paid_out,coalesce(sum(case when status in ('pending','processing') then amount else 0 end),0) pending_payouts from payout_requests where freelancer_id=%s""",(fid,))
            pr=cur.fetchone();paid=Decimal(str(pr['paid_out'] or 0));pending=Decimal(str(pr['pending_payouts'] or 0));available=max(Decimal('0'),net-paid-pending)
            if amount>available:
                c.rollback();return None,'insufficient_balance',available
            cur.execute("insert into payout_requests(freelancer_id,amount,note,status) values(%s,%s,%s,'pending') returning *",(fid,amount,str(note or '')[:500] or None))
            row=dict(cur.fetchone());c.commit()
            return {k:as_json(v) for k,v in row.items()},None,max(Decimal('0'),available-amount)
    except Exception:
        c.rollback();raise
    finally:
        c.close()

def friendly_device(user_agent):
    ua=str(user_agent or '')[:500]; low=ua.lower()
    if 'ipad' in low:return 'iPad'
    if 'iphone' in low:return 'iPhone'
    if 'android' in low and ('tv' in low or 'aft' in low):return 'Android TV'
    if 'android' in low:return 'Android'
    if 'windows' in low:return 'Windows'
    if 'macintosh' in low or 'mac os' in low:return 'Mac'
    if 'linux' in low:return 'Linux'
    return 'متصفح'


def log_account_activity(user_id,event_type,label,session_id=None,meta=None):
    try:q("insert into account_activity(user_id,session_id,event_type,label,meta) values(%s,%s,%s,%s,%s::jsonb)",(user_id,session_id,event_type,str(label or '')[:180],json.dumps(meta or {},ensure_ascii=False)),None)
    except Exception as e:print('ACCOUNT_ACTIVITY_ERR',repr(e),flush=True)

def admin_audit(admin_id,action,target_type=None,target_id=None,details=None):
    try:q("insert into admin_audit_logs(admin_id,action,target_type,target_id,details) values(%s,%s,%s,%s,%s::jsonb)",(admin_id,str(action)[:120],str(target_type or '')[:80] or None,str(target_id or '')[:120] or None,json.dumps(details or {},ensure_ascii=False)),None)
    except Exception as e:print('ADMIN_AUDIT_ERR',repr(e),flush=True)

def legal_versions(): return {'terms':LEGAL_TERMS_VERSION,'privacy':LEGAL_PRIVACY_VERSION,'marketplace_rules':LEGAL_MARKETPLACE_VERSION}

def legal_status(user_id):
    accepted={(x['document'],x['version']) for x in q('select document,version from legal_acceptances where user_id=%s',(user_id,))}
    docs={k:{'version':v,'accepted':(k,v) in accepted} for k,v in legal_versions().items()}
    return {'complete':all(x['accepted'] for x in docs.values()),'documents':docs}

def onboarding_status(user_id,role):
    legal=legal_status(user_id); pref=q('select onboarding_dismissed from user_preferences where user_id=%s',(user_id,),'one') or {}
    if role=='freelancer':
        fp=q('select bio,skills,is_available from freelancer_profiles where user_id=%s',(user_id,),'one') or {}; portfolio=q('select count(*)::int n from freelancer_portfolio where freelancer_id=%s',(user_id,),'one') or {'n':0}
        steps=[{'key':'legal','label':'موافقة الشروط والخصوصية','done':legal['complete'],'required':True},{'key':'profile','label':'إضافة نبذة مهنية','done':bool(str(fp.get('bio') or '').strip()),'required':True},{'key':'skills','label':'إضافة 3 مهارات على الأقل','done':len(fp.get('skills') or [])>=3,'required':True},{'key':'availability','label':'تحديد حالة التوفر','done':bool(fp.get('is_available')),'required':False},{'key':'portfolio','label':'إضافة نموذج عمل','done':int(portfolio.get('n') or 0)>0,'required':False}]
    else:
        cp=q('select company_name,city,sector,bio from client_profiles where user_id=%s',(user_id,),'one') or {}; tasks=q('select count(*)::int n from tasks where client_id=%s',(user_id,),'one') or {'n':0}
        steps=[{'key':'legal','label':'موافقة الشروط والخصوصية','done':legal['complete'],'required':True},{'key':'profile','label':'إكمال الملف المهني','done':bool(any(str(cp.get(k) or '').strip() for k in ('company_name','city','sector','bio'))),'required':False},{'key':'first_task','label':'نشر أول مهمة','done':int(tasks.get('n') or 0)>0,'required':False}]
    done=sum(1 for x in steps if x['done']); return {'role':role,'steps':steps,'completion_percent':round(100*done/max(1,len(steps))),'complete':all(x['done'] for x in steps if x['required']),'dismissed':bool(pref.get('onboarding_dismissed'))}

def auth(headers):
    h=headers.get('Authorization','')
    if not h.startswith('Bearer '): return None
    raw=h[7:]
    row=q("""select u.id,u.phone,u.name,u.role,u.is_verified,
                    s.id session_id,s.created_at session_created_at,s.expires_at session_expires_at,
                    s.last_seen_at session_last_seen_at,s.device_label session_device_label
             from sessions s join users u on u.id=s.user_id
             where s.token_hash=%s and s.revoked_at is null and s.expires_at>now() limit 1""",
          (sha(raw+SECRET),), 'one')
    if row:
        try:
            q("update sessions set last_seen_at=now() where id=%s and (last_seen_at is null or last_seen_at<now()-interval '10 minutes')",(row['session_id'],),None)
        except Exception:
            pass
    return row

def refresh_freelancer(fid):
    try:
        q("""update freelancer_profiles fp set rating=coalesce((select round(avg((quality+timeliness+communication)/3.0)::numeric,2) from reviews where reviewee_id=%s),0), completed_tasks=(select count(*)::int from orders where freelancer_id=%s and status='completed'), on_time_rate=coalesce((select round(100.0*avg(case when t.due_at is null or o.completed_at<=t.due_at then 1 else 0 end)::numeric,2) from orders o join tasks t on t.id=o.task_id where o.freelancer_id=%s and o.status='completed'),100) where fp.user_id=%s""",(fid,fid,fid,fid),None)
    except Exception:
        pass


def ensure_timeline_schema():
    q("""create table if not exists order_events(
        id bigserial primary key,
        order_id bigint not null references orders(id) on delete cascade,
        actor_id bigint references users(id),
        event_type text not null,
        title text not null,
        details text,
        meta jsonb not null default '{}'::jsonb,
        created_at timestamptz not null default now()
    );
    create index if not exists idx_order_events_order on order_events(order_id,created_at);""",(),None)

def log_order_event(order_id,event_type,title,actor_id=None,details=None,meta=None):
    try:
        q("insert into order_events(order_id,actor_id,event_type,title,details,meta) values(%s,%s,%s,%s,%s,%s::jsonb)",(order_id,actor_id,event_type,title,(details or None),json.dumps(meta or {},ensure_ascii=False)),None)
    except Exception as e:
        print('EVENT_ERR',repr(e),flush=True)

def order_timeline(order_id):
    o=q("select o.*,t.title task_title from orders o join tasks t on t.id=o.task_id where o.id=%s",(order_id,),'one')
    if not o:return []
    ev=[]
    def add(ts,kind,title,details=None,actor=None,meta=None):
        if not ts:return
        ev.append({'created_at':ts,'type':kind,'title':title,'details':details,'actor_name':actor,'meta':meta or {}})
    add(o.get('created_at'),'order_created','تم اختيار العرض وإنشاء الطلب',o.get('task_title'))
    for x in q("select e.*,u.name actor_name from order_events e left join users u on u.id=e.actor_id where e.order_id=%s order by e.created_at",(order_id,)):
        add(x.get('created_at'),x.get('event_type'),x.get('title'),x.get('details'),x.get('actor_name'),x.get('meta') or {})
    for x in q("select m.*,u.name actor_name,(select count(*)::int from attachments a where a.message_id=m.id) attachment_count from messages m join users u on u.id=m.sender_id where m.order_id=%s order by m.created_at",(order_id,)):
        body=str(x.get('body') or '')
        if body.startswith('طلب تعديل '):
            continue
        add(x.get('created_at'),'message','رسالة جديدة',body[:180],x.get('actor_name'),{'attachments':x.get('attachment_count') or 0})
    for x in q("select rr.*,u.name actor_name from order_revision_requests rr join users u on u.id=rr.requested_by where rr.order_id=%s order by rr.created_at",(order_id,)):
        add(x.get('created_at'),'revision_requested','طلب تعديل '+str(x.get('sequence_no')),x.get('note'),x.get('actor_name'),{'sequence_no':x.get('sequence_no'),'status':x.get('status')})
        if x.get('satisfied_at'):add(x.get('satisfied_at'),'revision_satisfied','تم تنفيذ التعديل '+str(x.get('sequence_no')),None,None,{'sequence_no':x.get('sequence_no')})
    for x in q("select d.*,u.name actor_name,(select count(*)::int from attachments a where a.delivery_id=d.id) attachment_count from deliveries d join users u on u.id=d.freelancer_id where d.order_id=%s order by d.created_at",(order_id,)):
        add(x.get('created_at'),'delivery','تم تسليم العمل',x.get('note'),x.get('actor_name'),{'attachments':x.get('attachment_count') or 0})
    for x in q("select d.*,uo.name opened_by_name,ur.name resolved_by_name from order_disputes d join users uo on uo.id=d.opened_by left join users ur on ur.id=d.resolved_by where d.order_id=%s order by d.created_at",(order_id,)):
        add(x.get('created_at'),'dispute_opened','تم فتح نزاع',x.get('reason'),x.get('opened_by_name'))
        if x.get('resolved_at'):
            ttl='تم استئناف الطلب بعد النزاع' if x.get('resolution_action')=='resume' else 'تم إلغاء الطلب بعد النزاع'
            add(x.get('resolved_at'),'dispute_resolved',ttl,x.get('resolution_note'),x.get('resolved_by_name'),{'action':x.get('resolution_action')})
    if o.get('completed_at'):add(o.get('completed_at'),'completed','اكتمل الطلب',None,None)
    r=q("select r.*,u.name actor_name from reviews r join users u on u.id=r.reviewer_id where r.order_id=%s",(order_id,),'one')
    if r:add(r.get('created_at'),'review','تم إضافة التقييم',r.get('comment'),r.get('actor_name'),{'quality':r.get('quality'),'timeliness':r.get('timeliness'),'communication':r.get('communication')})
    ev.sort(key=lambda x: str(x.get('created_at') or ''))
    return ev[-200:]


def ensure_services_schema():
    q("""create table if not exists services(
        id bigserial primary key,
        category_id bigint not null references categories(id),
        slug text unique not null,
        name_ar text not null,
        description_ar text,
        min_price numeric(10,2),
        max_price numeric(10,2),
        active boolean not null default true,
        created_at timestamptz not null default now()
    );
    create index if not exists idx_services_category on services(category_id,active,id);
    insert into services(category_id,slug,name_ar,description_ar,min_price,max_price)
    select c.id,v.slug,v.name_ar,v.description_ar,v.min_price,v.max_price
    from (values
        ('design','social-post-1','تصميم منشور سوشال واحد','تصميم منشور جاهز للنشر بالمقاس المطلوب',49,79),
        ('design','social-posts-3','تصميم 3 منشورات سوشال','ثلاثة تصاميم متناسقة لهوية الحساب',79,149),
        ('design','banner-ad','تصميم بانر أو إعلان','بانر رقمي أو إعلان بمقاس واحد',49,99),
        ('design','menu-price-list','تصميم منيو أو قائمة أسعار','تنسيق بصري احترافي لقائمة خدمات أو أسعار',99,249),
        ('design','business-card','تصميم بطاقة عمل','بطاقة عمل بوجه أو وجهين',49,99),
        ('design','simple-logo','تصميم شعار بسيط','شعار بسيط لمشروع صغير مع ملف نهائي',99,299),
        ('design','invitation-certificate','دعوة أو شهادة أو بطاقة','تصميم بطاقة مناسبة أو شهادة أو دعوة',49,99),
        ('design','resize-designs','تعديل مقاسات تصاميم','إعادة تجهيز التصاميم لمقاسات منصات مختلفة',49,99),
        ('files','ppt-10','عرض PowerPoint حتى 10 شرائح','تنسيق عرض واضح ومرتب حتى 10 شرائح',79,149),
        ('files','ppt-20','عرض PowerPoint حتى 20 شريحة','تنسيق عرض احترافي حتى 20 شريحة',149,299),
        ('files','word-format-20','تنسيق Word حتى 20 صفحة','تنسيق العناوين والجداول والهوامش والفهرسة البسيطة',49,99),
        ('files','pdf-tools','دمج أو ترتيب أو تحويل PDF','دمج وترتيب وتحويل ملفات PDF',49,79),
        ('files','word-pdf-form','إنشاء نموذج Word أو PDF','إنشاء نموذج منظم قابل للتعبئة أو الطباعة',49,99),
        ('design','cv-design','تصميم سيرة ذاتية','تنسيق سيرة ذاتية حديثة وواضحة',79,149),
        ('design','company-profile','بروفايل شركة صغير','تصميم ملف تعريفي مختصر لشركة أو مشروع',149,299),
        ('excel','excel-clean','تنظيف وتنسيق Excel','تنظيف الجدول وتوحيد التنسيق والقيم',49,99),
        ('excel','excel-formulas','معادلات Excel','إضافة أو إصلاح معادلات وصيغ Excel',79,149),
        ('excel','excel-charts','رسوم وتقرير Excel','إنشاء رسوم بيانية وتقرير مختصر من البيانات',79,149),
        ('excel','excel-dashboard','Dashboard Excel بسيط','لوحة مؤشرات بسيطة ومترابطة داخل Excel',149,299),
        ('excel','data-entry-300','إدخال بيانات حتى 300 صف','إدخال وتنظيم بيانات حتى 300 صف',49,99),
        ('excel','merge-dedupe','دمج وإزالة تكرار البيانات','دمج ملفات أو جداول وإزالة السجلات المكررة',49,99),
        ('excel','google-sheet','تنظيم Google Sheet','إعداد جدول منظم وسهل الاستخدام',79,149),
        ('writing','product-desc-10','كتابة 10 أوصاف منتجات','أوصاف منتجات مختصرة وواضحة للبيع الإلكتروني',59,119),
        ('writing','social-copy-10','كتابة 10 منشورات سوشال','نصوص جاهزة للنشر لوسائل التواصل',79,149),
        ('writing','proofread-1500','تدقيق 1500 كلمة','تدقيق لغوي وإملائي حتى 1500 كلمة',49,79),
        ('writing','rewrite-1500','إعادة صياغة 1500 كلمة','إعادة صياغة تحافظ على المعنى وتحسن الأسلوب',49,99),
        ('translation','translate-1000','ترجمة حتى 1000 كلمة','ترجمة نص حتى 1000 كلمة بين اللغات المدعومة',59,129),
        ('writing','transcribe-30','تفريغ صوت حتى 30 دقيقة','تحويل تسجيل صوتي إلى نص منظم',59,129),
        ('writing','summarize-30','تلخيص حتى 30 صفحة','تلخيص محتوى طويل إلى نقاط وأفكار أساسية',59,129),
        ('business','research-sources','جمع مصادر ومعلومات','جمع معلومات عامة ومصادر مرتبة حول موضوع محدد',59,149),
        ('design','remove-bg-20','إزالة خلفية حتى 20 صورة','قص وإزالة الخلفيات وتسليم PNG',49,79),
        ('design','retouch-5','تحسين 5 صور','تحسين إضاءة وألوان وتنظيف بسيط لخمس صور',59,119),
        ('design','product-images-3','تجهيز 3 صور منتجات','تهيئة صور منتجات نظيفة ومتناسقة للمتجر',59,129),
        ('video','reel-under-1','مونتاج Reel أقل من دقيقة','مونتاج فيديو قصير مع قص وانتقالات بسيطة',79,149),
        ('video','subtitles-5','إضافة ترجمة لفيديو حتى 5 دقائق','إضافة نصوص أو ترجمة زمنية لفيديو قصير',59,119),
        ('video','video-1-3','مونتاج فيديو 1–3 دقائق','مونتاج فيديو متوسط مع ترتيب المقاطع والصوت',119,299),
        ('video','audio-clean-15','تنظيف صوت حتى 15 دقيقة','تقليل ضوضاء وتحسين مستوى الصوت',59,129),
        ('design','thumbnail-cover','تصميم صورة مصغرة أو غلاف','غلاف أو Thumbnail جذاب بمقاس واحد',49,79),
        ('business','upload-products-20','رفع 20 منتج','إدخال بيانات وصور 20 منتج في متجر إلكتروني',79,149),
        ('excel','product-file-50','تجهيز ملف 50 منتج','تنظيم بيانات حتى 50 منتج في ملف جاهز',79,149),
        ('design','quotation-design','تصميم قائمة أسعار أو عرض سعر','تصميم عرض سعر أو قائمة أسعار مرتبة',59,119),
        ('business','content-plan-2w','خطة محتوى لأسبوعين','خطة نشر وأفكار محتوى لمدة أسبوعين',99,199),
        ('business','competitors-5','مقارنة 5 منافسين','مقارنة عامة ومنظمة لخمس جهات منافسة',99,199),
        ('business','businesses-30','جمع بيانات 30 نشاطًا','جمع معلومات عامة متاحة لثلاثين نشاطًا تجاريًا',79,149),
        ('writing','meeting-summary','تلخيص اجتماع أو تسجيل','تلخيص القرارات والنقاط المهمة من اجتماع أو تسجيل',59,129),
        ('writing','cs-replies-15','صياغة 15 رد خدمة عملاء','ردود جاهزة ومهنية لسيناريوهات خدمة العملاء',59,129),
        ('ai','ai-prompts','إعداد Prompts أو Workflow بالذكاء الاصطناعي','صياغة تعليمات وقوالب استخدام عملية للذكاء الاصطناعي',79,149),
        ('ai','ai-classify-data','تصنيف بيانات غير حساسة بالذكاء الاصطناعي','تنظيم وتصنيف بيانات غير حساسة وفق قواعد واضحة',79,199),
        ('ai','no-code-automation','أتمتة No-code بسيطة','إعداد أتمتة بسيطة بين أدوات مدعومة',149,299),
        ('business','cms-edits','تعديلات محتوى CMS بسيطة','تحديث نصوص وصور ومحتوى بسيط داخل نظام إدارة محتوى',79,199)
    ) as v(category_slug,slug,name_ar,description_ar,min_price,max_price)
    join categories c on c.slug=v.category_slug
    on conflict(slug) do update set category_id=excluded.category_id,name_ar=excluded.name_ar,description_ar=excluded.description_ar,min_price=excluded.min_price,max_price=excluded.max_price,active=true;""",(),None)

def ensure_roles_schema():
    q("""create table if not exists user_roles(
        user_id bigint not null references users(id) on delete cascade,
        role text not null check(role in ('client','freelancer','admin')),
        enabled boolean not null default true,
        created_at timestamptz not null default now(),
        primary key(user_id,role)
    );
    create index if not exists idx_user_roles_role on user_roles(role,user_id);
    insert into user_roles(user_id,role,enabled)
      select id,role,true from users
      on conflict(user_id,role) do update set enabled=true;
    insert into user_roles(user_id,role,enabled)
      select user_id,'freelancer',true from freelancer_profiles
      on conflict(user_id,role) do update set enabled=true;""",(),None)

def enabled_roles(user_id):
    return [x['role'] for x in q("select role from user_roles where user_id=%s and enabled=true order by case role when 'admin' then 0 when 'client' then 1 else 2 end,role",(user_id,))]

def ensure_notifications_schema():
    q("""create table if not exists user_notifications_v2(
        id bigserial primary key,
        user_id bigint not null references users(id) on delete cascade,
        order_id bigint references orders(id) on delete cascade,
        kind text not null default 'general',
        title text not null,
        body text,
        read_at timestamptz,
        created_at timestamptz not null default now()
    );
    create index if not exists idx_user_notifications_v2_user on user_notifications_v2(user_id,created_at desc);
    create index if not exists idx_user_notifications_v2_unread on user_notifications_v2(user_id,read_at,created_at desc);""",(),None)

def ensure_engagement_schema():
    q("""create table if not exists client_profiles(
        user_id bigint primary key references users(id) on delete cascade,
        company_name text,bio text,city text,sector text,updated_at timestamptz not null default now()
    );
    create table if not exists favorite_tasks(
        freelancer_id bigint not null references users(id) on delete cascade,
        task_id bigint not null references tasks(id) on delete cascade,
        created_at timestamptz not null default now(),
        primary key(freelancer_id,task_id)
    );
    create index if not exists idx_favorite_tasks_freelancer on favorite_tasks(freelancer_id,created_at desc);
    create table if not exists saved_task_searches(
        id bigserial primary key,freelancer_id bigint not null references users(id) on delete cascade,
        name text not null,filters jsonb not null default '{}'::jsonb,created_at timestamptz not null default now(),updated_at timestamptz not null default now()
    );
    create index if not exists idx_saved_task_searches_freelancer on saved_task_searches(freelancer_id,created_at desc);
    alter table user_notifications_v2 add column if not exists task_id bigint references tasks(id) on delete cascade;
    create index if not exists idx_user_notifications_v2_task on user_notifications_v2(user_id,task_id,created_at desc) where task_id is not null;""",(),None)

def notify(user_id,title,body=None,kind='general',order_id=None,task_id=None):
    try:
        q("insert into user_notifications_v2(user_id,order_id,task_id,kind,title,body) values(%s,%s,%s,%s,%s,%s)",(user_id,order_id,task_id,kind,title[:180],(body or '')[:1200] or None),None)
    except Exception as e:
        print('NOTIFY_ERR',repr(e),flush=True)

def notify_admins(title,body=None,kind='admin',order_id=None,task_id=None):
    try:
        for a in q("select id from users where role='admin' order by id"):
            notify(a['id'],title,body,kind,order_id,task_id)
    except Exception:
        pass

def interaction_restricted(a,b):
    try:
        a=int(a);b=int(b)
    except Exception:
        return True
    if a==b:return False
    return bool(q("""select 1 where
        exists(select 1 from user_blocks ub where (ub.blocker_id=%s and ub.blocked_id=%s) or (ub.blocker_id=%s and ub.blocked_id=%s))
        or exists(select 1 from user_moderation um where um.interaction_restricted=true and um.user_id in (%s,%s))
        limit 1""",(a,b,b,a,a,b),'one'))

def task_hidden(task_id):
    try:return bool(q('select 1 from task_moderation where task_id=%s and hidden=true',(int(task_id),),'one'))
    except Exception:return False

class H(BaseHTTPRequestHandler):
    server_version=f'MINJAZ/{VERSION}'
    def request_id(self):
        if not hasattr(self,'_request_id'):
            incoming=str(self.headers.get('X-Request-ID') or '').strip()[:80]
            self._request_id=incoming if re.fullmatch(r'[A-Za-z0-9._:-]{8,80}',incoming or '') else uuid.uuid4().hex
        return self._request_id
    def client_key(self):
        ip=str(self.client_address[0] if self.client_address else '')
        return sha(ip+':'+SECRET)[:32] if ip else 'unknown'
    def log_message(self, fmt,*args): print('REQ',self.request_id(),fmt%args, flush=True)
    def _headers(self,status=200,ctype='application/json; charset=utf-8'):
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Request-ID',self.request_id())
        self.send_header('X-Frame-Options','DENY'); self.send_header('Referrer-Policy','strict-origin-when-cross-origin'); self.send_header('Permissions-Policy','geolocation=(), camera=(), microphone=()'); self.send_header('Strict-Transport-Security','max-age=31536000; includeSubDomains'); self.send_header('Cross-Origin-Opener-Policy','same-origin'); self.send_header('X-Permitted-Cross-Domain-Policies','none')
        csp=f"default-src 'self'; object-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: https:; connect-src 'self'{STORAGE_CSP_CONNECT}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if IS_PROD: csp+='; upgrade-insecure-requests'
        self.send_header('Content-Security-Policy',csp)
        if not IS_PROD:self.send_header('X-Robots-Tag','noindex, nofollow, noarchive')
        origin=(self.headers.get('Origin') or '').rstrip('/')
        if origin and origin in CORS_ORIGINS:
            self.send_header('Access-Control-Allow-Origin',origin); self.send_header('Vary','Origin')
        self.send_header('Access-Control-Allow-Headers','content-type,authorization'); self.send_header('Access-Control-Allow-Methods','GET,POST,PATCH,DELETE,OPTIONS'); self.end_headers()
    def sendj(self,status,obj):
        if isinstance(obj,dict) and status>=400 and 'request_id' not in obj: obj={**obj,'request_id':self.request_id()}
        self._headers(status); self.wfile.write(json.dumps(obj,ensure_ascii=False,default=as_json).encode())
    def raw_body(self):
        if hasattr(self,'_raw_body_cache'): return self._raw_body_cache
        n=int(self.headers.get('Content-Length','0') or 0)
        if n>2_000_000: raise ValueError('too_large')
        self._raw_body_cache=self.rfile.read(n) if n else b''
        return self._raw_body_cache
    def body(self):
        raw=self.raw_body()
        try:
            return json.loads(raw or b'{}')
        except json.JSONDecodeError as exc:
            raise ValueError('invalid_json') from exc
    def require(self,role=None):
        u=auth(self.headers)
        if not u: self.sendj(401,{'error':'unauthorized'}); return None
        if role and u.get('role')!=role: self.sendj(403,{'error':role+'_only'}); return None
        return u
    def do_OPTIONS(self): self._headers(204)
    def do_GET(self): self.route('GET')
    def do_POST(self): self.route('POST')
    def do_PATCH(self): self.route('PATCH')
    def do_DELETE(self): self.route('DELETE')
    def route(self,method):
        try:
            parsed=urlparse(self.path); p=parsed.path; query=parse_qs(parsed.query)
            if p=='/health':
                started=datetime.now(); now=q('select now() now',(), 'one')['now']; latency=max(0,int((datetime.now()-started).total_seconds()*1000)); return self.sendj(200,{'ok':True,'service':'minjaz-python-unified','database':True,'database_latency_ms':latency,'payment_mode':PAYMENT_MODE,'environment':APP_ENV,'now':now,'version':VERSION})
            if method=='GET' and p=='/readiness':
                checks=[
                    {'key':'app_environment','ok':APP_ENV=='production','value':APP_ENV,'required':True},
                    {'key':'database_persistence','ok':DB_PERSISTENCE=='persistent','value':DB_PERSISTENCE,'required':True},
                    {'key':'sms_provider','ok':SMS_MODE=='adapter' and _https_url(SMS_WEBHOOK_URL) and len(SMS_WEBHOOK_BEARER)>=16,'value':SMS_MODE,'required':True},
                    {'key':'payment_provider','ok':PAYMENT_MODE=='adapter' and _https_url(PAYMENT_CREATE_URL) and len(PAYMENT_ADAPTER_BEARER)>=16 and len(PAYMENT_WEBHOOK_SECRET)>=32,'value':PAYMENT_MODE,'required':True},
                    {'key':'file_storage','ok':STORAGE_MODE=='railway_bucket' and BUCKET_READY,'value':STORAGE_MODE+(' (configured)' if BUCKET_READY else ' (not configured)'),'required':True},
                    {'key':'kyc_provider','ok':KYC_MODE=='adapter' and _https_url(KYC_START_URL) and len(KYC_ADAPTER_BEARER)>=16 and len(KYC_WEBHOOK_SECRET)>=32,'value':KYC_MODE,'required':True},
                    {'key':'source_control','ok':SOURCE_CONTROL not in ('railway_env','none',''),'value':SOURCE_CONTROL,'required':True},
                    {'key':'legal_versions','ok':all(legal_versions().values()),'value':','.join(legal_versions().values()),'required':True},
                    {'key':'legal_review','ok':LEGAL_REVIEW_STATUS=='approved','value':LEGAL_REVIEW_STATUS,'required':True},
                    {'key':'public_base_url','ok':_https_url(PUBLIC_BASE_URL),'value':PUBLIC_BASE_URL or 'missing','required':True},
                    {'key':'cors_origins','ok':bool(CORS_ORIGINS) and '*' not in CORS_ORIGINS and all(_https_url(x) for x in CORS_ORIGINS),'value':','.join(sorted(CORS_ORIGINS)),'required':True},
                    {'key':'runtime_schema_ensure','ok':not RUN_RUNTIME_SCHEMA_ENSURE,'value':'off' if not RUN_RUNTIME_SCHEMA_ENSURE else 'on','required':True},
                    {'key':'operational_telemetry','ok':True,'value':'operational_events enabled','required':False},
                    {'key':'launch_guard','ok':(not IS_PROD) or not production_blockers(),'value':'hard-enforced in production','required':False}
                ]
                commercial=all(x['ok'] for x in checks if x['required']); beta_keys=('database_persistence','source_control','legal_versions'); beta=all(x['ok'] for x in checks if x['key'] in beta_keys)
                status=503 if IS_PROD and not commercial else 200
                return self.sendj(status,{'ready_for_beta':beta,'ready_for_commercial_launch':commercial,'checks':checks,'version':VERSION})
            if method=='POST' and p=='/api/v1/integrations/kyc/webhook':
                if KYC_MODE!='adapter' or len(KYC_WEBHOOK_SECRET)<32:return self.sendj(503,{'error':'kyc_webhook_not_configured'})
                raw=self.raw_body(); supplied=str(self.headers.get('X-Minjaz-Signature') or '').strip().lower()
                expected=hmac.new(KYC_WEBHOOK_SECRET.encode('utf-8'),raw,hashlib.sha256).hexdigest()
                if not supplied or not hmac.compare_digest(supplied,expected):return self.sendj(401,{'error':'invalid_signature'})
                try:b=json.loads(raw or b'{}')
                except json.JSONDecodeError:return self.sendj(400,{'error':'invalid_json'})
                try:result=apply_kyc_adapter_event(b)
                except AdapterEventError as exc:return self.sendj(exc.status,{'error':exc.code})
                if result.get('duplicate'):return self.sendj(200,{'ok':True,'duplicate':True})
                if result.get('changed'):notify(result['user_id'],'تحديث توثيق الهوية',{'approved':'تم اعتماد التوثيق','rejected':'تعذر اعتماد التوثيق','pending':'التوثيق قيد المراجعة'}[result['status']],'kyc')
                return self.sendj(200,{'ok':True})
            if method=='POST' and p=='/api/v1/integrations/payments/webhook':
                if PAYMENT_MODE!='adapter' or len(PAYMENT_WEBHOOK_SECRET)<32:return self.sendj(503,{'error':'payment_webhook_not_configured'})
                raw=self.raw_body(); supplied=str(self.headers.get('X-Minjaz-Signature') or '').strip().lower()
                expected=hmac.new(PAYMENT_WEBHOOK_SECRET.encode('utf-8'),raw,hashlib.sha256).hexdigest()
                if not supplied or not hmac.compare_digest(supplied,expected):return self.sendj(401,{'error':'invalid_signature'})
                try:b=json.loads(raw or b'{}')
                except json.JSONDecodeError:return self.sendj(400,{'error':'invalid_json'})
                try:result=apply_payment_adapter_event(b)
                except AdapterEventError as exc:return self.sendj(exc.status,{'error':exc.code})
                if result.get('duplicate'):return self.sendj(200,{'ok':True,'duplicate':True})
                o=result['order']; event_id=result['event_id']
                if result['event_type']=='payment.succeeded' and result.get('workflow_started'):
                    log_order_event(o['id'],'payment','تم تأكيد الدفع من مزود الدفع',None,meta={'mode':'adapter','event_id':event_id});notify(o['freelancer_id'],'تم دفع الطلب','تقدر تبدأ التنفيذ الآن','payment',o['id'])
                elif result['event_type']=='payment.succeeded' and result.get('late_cancelled_payment'):
                    log_order_event(o['id'],'late_payment','وصل تأكيد دفع بعد إلغاء الطلب؛ يلزم استرداد/مراجعة مالية',None,meta={'mode':'adapter','event_id':event_id});notify(o['client_id'],'وصل دفع بعد إلغاء الطلب','سجلنا العملية للمراجعة والاسترداد بدون إعادة فتح التنفيذ','payment',o['id']);notify_admins('دفع متأخر بعد إلغاء طلب',f"الطلب #{o['id']} يحتاج مراجعة واسترداد",'payment',o['id'])
                elif result['event_type']=='payment.succeeded' and result.get('changed'):
                    log_order_event(o['id'],'payment_reconciliation','تم تسجيل دفع في حالة طلب غير متوقعة للمراجعة',None,meta={'mode':'adapter','event_id':event_id});notify_admins('دفع يحتاج مطابقة يدوية',f"الطلب #{o['id']} كان في حالة {o.get('status')}",'payment',o['id'])
                if result['event_type']=='payment.failed' and result.get('failed_effective'):
                    log_order_event(o['id'],'payment_failed','تعذر تأكيد الدفع من مزود الدفع',None,meta={'mode':'adapter','event_id':event_id});notify(o['client_id'],'تعذر تأكيد الدفع','يمكنك إعادة المحاولة من رابط الدفع أو التواصل مع الدعم','payment',o['id'])
                return self.sendj(200,{'ok':True})
            if method=='GET' and p=='/api/v1/legal/documents':
                return self.sendj(200,{'documents':[
                    {'key':'terms','title':'شروط استخدام مِنجاز','version':LEGAL_TERMS_VERSION,'review_status':('approved' if LEGAL_REVIEW_STATUS=='approved' else 'draft_pending_legal_review'),'sections':['استخدام المنصة للخدمات الرقمية المسموحة فقط.','يلتزم المستخدم بالمعلومات الصحيحة وعدم تجاوز المنصة أثناء الطلب.','المدفوعات والاستردادات والنزاعات تخضع لحالة الطلب ومزود الدفع عند تفعيله.','النص القانوني الحالي مسودة Beta ويحتاج اعتمادًا قانونيًا قبل الإطلاق التجاري.']},
                    {'key':'privacy','title':'سياسة الخصوصية','version':LEGAL_PRIVACY_VERSION,'review_status':('approved' if LEGAL_REVIEW_STATUS=='approved' else 'draft_pending_legal_review'),'sections':['نستخدم بيانات الحساب لتشغيل المنصة والأمان والدعم وتنفيذ الطلبات.','لا نعرض رقم الجوال في الملفات العامة أو تفاصيل المهمة للطرف الآخر.','يمكن تقديم طلب وصول أو تصحيح أو حذف أو تقييد من صفحة الحساب.','سياسة الاحتفاظ النهائية ومزودو المعالجة يحتاجون اعتمادًا قانونيًا قبل الإطلاق التجاري.']},
                    {'key':'marketplace_rules','title':'قواعد سوق مِنجاز','version':LEGAL_MARKETPLACE_VERSION,'review_status':('approved' if LEGAL_REVIEW_STATUS=='approved' else 'draft_pending_legal_review'),'sections':['يُمنع الاحتيال والانتحال والخدمات المحظورة والمحتوى المؤذي.','العروض خاصة والعميل يختار العرض قبل الدفع والتنفيذ.','الحظر يمنع التعاملات الجديدة ولا يقطع حقوق الأطراف في الطلبات القائمة.','يمكن لفريق الأمان إخفاء مهمة أو تقييد تعاملات جديدة بعد المراجعة.']}
                ]})
            if method=='GET' and p in ('/','/index.html'):
                data=open(HTML_PATH,'rb').read(); self._headers(200,'text/html; charset=utf-8'); return self.wfile.write(data)
            if method=='GET' and p in ('/manifest.webmanifest','/sw.js','/icon.svg'):
                static_name={'/manifest.webmanifest':'manifest.webmanifest','/sw.js':'sw.js','/icon.svg':'icon.svg'}[p]
                ctype={'/manifest.webmanifest':'application/manifest+json; charset=utf-8','/sw.js':'application/javascript; charset=utf-8','/icon.svg':'image/svg+xml; charset=utf-8'}[p]
                data=open(os.path.join(os.path.dirname(HTML_PATH),static_name),'rb').read(); self._headers(200,ctype); return self.wfile.write(data)
            if p=='/favicon.ico': self._headers(204); return
            if method=='GET' and p=='/api/v1/storage/config':
                return self.sendj(200,{'mode':STORAGE_MODE,'direct_uploads':STORAGE_MODE=='railway_bucket' and BUCKET_READY,'max_upload_bytes':BUCKET_STORAGE.max_bytes,'allowed_extensions':sorted(ALLOWED_TYPES)})
            if method=='POST' and p=='/api/v1/uploads/presign':
                u=self.require();
                if not u:return
                if STORAGE_MODE!='railway_bucket' or not BUCKET_READY:return self.sendj(503,{'error':'storage_not_configured'})
                b=self.body()
                try: meta=BUCKET_STORAGE.validate_meta(b.get('file_name'),b.get('mime_type'),b.get('size_bytes'))
                except StorageError as e:return self.sendj(400,{'error':str(e),'max_upload_bytes':BUCKET_STORAGE.max_bytes})
                q("delete from upload_intents where consumed_at is null and expires_at<now()-interval '24 hours'",(),None)
                recent=q("select count(*)::int n from upload_intents where user_id=%s and created_at>now()-interval '10 minutes'",(u['id'],),'one')['n']
                if recent>=20:return self.sendj(429,{'error':'upload_rate_limited','retry_after_seconds':600})
                key=BUCKET_STORAGE.object_key(u['id'],meta['extension'])
                q("insert into upload_intents(user_id,object_key,file_name,mime_type,size_bytes,expires_at) values(%s,%s,%s,%s,%s,now()+interval '20 minutes')",(u['id'],key,meta['file_name'],meta['mime_type'],meta['size_bytes']),None)
                return self.sendj(201,{'key':key,'upload_url':BUCKET_STORAGE.presign('PUT',key,expires=900,content_type=meta['mime_type']),'headers':{'Content-Type':meta['mime_type']},'expires_in_seconds':900,'max_upload_bytes':BUCKET_STORAGE.max_bytes})
            if method=='POST' and p=='/api/v1/uploads/complete':
                u=self.require();
                if not u:return
                if STORAGE_MODE!='railway_bucket' or not BUCKET_READY:return self.sendj(503,{'error':'storage_not_configured'})
                b=self.body();key=str(b.get('key') or '').strip().lstrip('/')
                if not BUCKET_STORAGE.safe_key_for_user(key,u['id']):return self.sendj(403,{'error':'invalid_upload_key'})
                intent=q("select * from upload_intents where user_id=%s and object_key=%s and expires_at>now()",(u['id'],key),'one')
                if not intent:return self.sendj(404,{'error':'upload_intent_not_found'})
                if intent.get('completed_at'):
                    return self.sendj(200,{'attachment':{'name':intent['file_name'],'storage_key':key,'mime_type':intent['mime_type'],'size_bytes':intent['size_bytes']}})
                try: actual=BUCKET_STORAGE.head(key)
                except Exception as e:
                    print('UPLOAD_HEAD_ERR',repr(e),flush=True);return self.sendj(409,{'error':'upload_not_found'})
                if int(actual.get('size_bytes') or 0)!=int(intent['size_bytes']) or actual.get('mime_type')!=intent['mime_type']:
                    BUCKET_STORAGE.delete(key)
                    return self.sendj(409,{'error':'upload_verification_failed'})
                q("update upload_intents set completed_at=now(),etag=%s where id=%s",(actual.get('etag') or None,intent['id']),None)
                return self.sendj(200,{'attachment':{'name':intent['file_name'],'storage_key':key,'mime_type':intent['mime_type'],'size_bytes':intent['size_bytes']}})
            if method=='GET' and p=='/api/v1/services': return self.sendj(200,{'items':q('select s.id,s.slug,s.name_ar,s.description_ar,s.min_price,s.max_price,s.category_id,c.name_ar category_name,c.icon category_icon from services s join categories c on c.id=s.category_id where s.active=true order by s.category_id,s.id')})
            if method=='GET' and p=='/api/v1/categories': return self.sendj(200,{'items':q('select id,slug,name_ar,icon from categories order by id')})
            if method=='POST' and p=='/api/v1/auth/request-otp':
                b=self.body(); phone=normalize_phone(b.get('phone',''))
                if not phone:return self.sendj(400,{'error':'invalid_phone'})
                if not rate_limit_event('otp_ip',self.client_key(),20,600):return self.sendj(429,{'error':'otp_source_rate_limited','retry_after_seconds':600})
                r=q("select count(*)::int n,max(created_at) last,extract(epoch from (now()-max(created_at)))::float8 age_seconds from otp_challenges where phone=%s and created_at>now()-interval '10 minutes'",(phone,), 'one')
                if r['n']>=5:return self.sendj(429,{'error':'otp_rate_limited','retry_after_seconds':600})
                if r['last'] and float(r.get('age_seconds') or 999999)<60:return self.sendj(429,{'error':'otp_wait','retry_after_seconds':60})
                cid=str(uuid.uuid4())
                if SMS_MODE=='dev':
                    if IS_PROD:return self.sendj(503,{'error':'sms_not_configured'})
                    code=DEV_OTP; delivery='development'
                elif SMS_MODE=='adapter':
                    code=f'{secrets.randbelow(1000000):06d}'; delivery='adapter'
                    try: adapter_post_json(SMS_WEBHOOK_URL,{'challenge_id':cid,'phone':phone,'code':code,'purpose':'login','expires_in_seconds':600},SMS_WEBHOOK_BEARER)
                    except Exception as exc:
                        operational_event('error','sms','delivery_failed',repr(exc),self.request_id(),None,'phone',sha(phone)[:16]);print('SMS_ADAPTER_ERR',self.request_id(),repr(exc),flush=True);return self.sendj(502,{'error':'sms_delivery_failed'})
                else:
                    return self.sendj(503,{'error':'sms_not_configured'})
                q("insert into otp_challenges(challenge_id,phone,code_hash,purpose,expires_at) values(%s,%s,%s,'login',now()+interval '10 minutes')",(cid,phone,sha(cid+':'+code+':'+SECRET)),None)
                return self.sendj(201,{'challenge_id':cid,'expires_in_seconds':600,'delivery':delivery,'code_length':len(code),**({'dev_code':code} if delivery=='development' else {})})
            if method=='POST' and p=='/api/v1/auth/verify-otp':
                b=self.body(); cid=str(b.get('challenge_id','')); code=str(b.get('code','')); role=b.get('role') if b.get('role') in ('client','freelancer') else 'client'; name=str(b.get('name') or 'مستخدم').strip()[:120]
                ch=q("select *,expires_at<=now() expired from otp_challenges where challenge_id=%s",(cid,), 'one')
                if not ch:return self.sendj(404,{'error':'challenge_not_found'})
                if ch.get('verified_at'):return self.sendj(409,{'error':'already_verified'})
                if ch.get('expired'):return self.sendj(410,{'error':'otp_expired'})
                if ch['attempts']>=5:return self.sendj(429,{'error':'too_many_attempts'})
                if sha(cid+':'+code+':'+SECRET)!=ch['code_hash']:
                    q('update otp_challenges set attempts=attempts+1 where id=%s',(ch['id'],),None); return self.sendj(401,{'error':'invalid_code'})
                q('update otp_challenges set verified_at=now() where id=%s',(ch['id'],),None)
                if ADMIN_PHONE and ch['phone']==ADMIN_PHONE: role='admin'
                u=q('select * from users where phone=%s',(ch['phone'],), 'one')
                if not u:
                    u=q('insert into users(phone,name,role,is_verified) values(%s,%s,%s,true) returning *',(ch['phone'],name,role),'one')
                else:
                    q('update users set name=%s,is_verified=true where id=%s',(name,u['id']),None)
                q("insert into user_roles(user_id,role,enabled) values(%s,%s,true) on conflict(user_id,role) do update set enabled=true",(u['id'],role),None)
                if role=='freelancer': q("insert into freelancer_profiles(user_id) values(%s) on conflict(user_id) do nothing",(u['id'],),None)
                q('update users set role=%s where id=%s',(role,u['id']),None)
                u=q('select * from users where id=%s',(u['id'],),'one')
                roles=enabled_roles(u['id'])
                raw=secrets.token_hex(32); ua=str(self.headers.get('User-Agent') or '')[:500]; ip=str(self.client_address[0] if self.client_address else '')
                ss=q("insert into sessions(user_id,token_hash,expires_at,user_agent,device_label,ip_hash,last_seen_at) values(%s,%s,now()+(%s || ' days')::interval,%s,%s,%s,now()) returning id",(u['id'],sha(raw+SECRET),SESSION_TTL_DAYS,ua,friendly_device(ua),sha(ip+SECRET)[:24] if ip else None),'one')
                log_account_activity(u['id'],'login','تسجيل دخول ناجح',ss.get('id') if ss else None,{'device':friendly_device(ua)})
                user={k:as_json(u.get(k)) for k in ('id','phone','name','role')}; user['roles']=roles
                return self.sendj(200,{'token':raw,'user':user,'roles':roles})
            if method=='POST' and p=='/api/v1/auth/logout':
                u=self.require();
                if not u:return
                raw=self.headers.get('Authorization','')[7:]; q('update sessions set revoked_at=now() where token_hash=%s',(sha(raw+SECRET),),None);log_account_activity(u['id'],'logout','تسجيل الخروج',u.get('session_id'));return self.sendj(200,{'ok':True})
            if method=='GET' and p=='/api/v1/me':
                u=self.require();
                if not u:return
                roles=enabled_roles(u['id'])
                if not roles:
                    q("insert into user_roles(user_id,role,enabled) values(%s,%s,true) on conflict(user_id,role) do update set enabled=true",(u['id'],u['role']),None); roles=enabled_roles(u['id'])
                prof=q('select * from freelancer_profiles where user_id=%s',(u['id'],),'one') if 'freelancer' in roles else None
                user={k:as_json(u.get(k)) for k in ('id','phone','name','role','is_verified')}; user['roles']=roles
                return self.sendj(200,{'user':user,'roles':roles,'freelancer_profile':prof})
            if p=='/api/v1/me/profile' and method=='PATCH':
                u=self.require();
                if not u:return
                b=self.body();name=str(b.get('name') or '').strip()[:120]
                if len(name)<2:return self.sendj(400,{'error':'invalid_name'})
                r=q('update users set name=%s where id=%s returning id,phone,name,role,is_verified',(name,u['id']),'one');log_account_activity(u['id'],'profile_updated','تم تحديث الاسم الظاهر',u.get('session_id'));return self.sendj(200,r)
            if p=='/api/v1/privacy/export' and method=='GET':
                u=self.require();
                if not u:return
                uid=u['id'];order_ids=[x['id'] for x in q('select id from orders where client_id=%s or freelancer_id=%s order by created_at desc limit 500',(uid,uid))]
                messages=[]
                if order_ids:
                    messages=q('select m.id,m.order_id,m.sender_id,m.body,m.created_at from messages m where m.order_id=any(%s) order by m.created_at limit 3000',(order_ids,))
                data={
                    'account':q('select id,phone,name,role,is_verified,created_at from users where id=%s',(uid,),'one'),
                    'roles':enabled_roles(uid),
                    'client_profile':q('select * from client_profiles where user_id=%s',(uid,),'one'),
                    'freelancer_profile':q('select * from freelancer_profiles where user_id=%s',(uid,),'one'),
                    'tasks':q('select * from tasks where client_id=%s order by created_at desc limit 1000',(uid,)),
                    'proposals':q('select * from proposals where freelancer_id=%s order by created_at desc limit 1000',(uid,)),
                    'orders':q('select * from orders where client_id=%s or freelancer_id=%s order by created_at desc limit 1000',(uid,uid)),
                    'messages':messages,
                    'reviews':q('select * from reviews where reviewer_id=%s or reviewee_id=%s order by created_at desc limit 1000',(uid,uid)),
                    'support_tickets':q('select * from support_tickets where user_id=%s order by created_at desc limit 500',(uid,)),
                    'privacy_requests':q('select * from privacy_requests where user_id=%s order by created_at desc limit 500',(uid,)),
                    'activity':q('select event_type,label,meta,created_at from account_activity where user_id=%s order by created_at desc limit 500',(uid,)),
                    'legal_acceptances':q('select document,version,accepted_at from legal_acceptances where user_id=%s order by accepted_at desc',(uid,))
                }
                log_account_activity(uid,'privacy_export','تم إنشاء تصدير بيانات الحساب',u.get('session_id'))
                return self.sendj(200,{'generated_at':datetime.now().astimezone().isoformat(),'version':VERSION,'data':data})
            if p=='/api/v1/account/preferences':
                u=self.require();
                if not u:return
                if method=='GET':
                    pref=q("select opportunity_alerts,product_updates,marketing,onboarding_dismissed,updated_at from user_preferences where user_id=%s",(u['id'],),'one')
                    if not pref:pref=q("insert into user_preferences(user_id) values(%s) returning opportunity_alerts,product_updates,marketing,onboarding_dismissed,updated_at",(u['id'],),'one')
                    return self.sendj(200,pref)
                if method=='PATCH':
                    b=self.body();cur=q("select * from user_preferences where user_id=%s",(u['id'],),'one') or {}; ks=('opportunity_alerts','product_updates','marketing','onboarding_dismissed'); vals={k:bool(b[k]) if k in b else bool(cur.get(k,False)) for k in ks}
                    r=q("insert into user_preferences(user_id,opportunity_alerts,product_updates,marketing,onboarding_dismissed) values(%s,%s,%s,%s,%s) on conflict(user_id) do update set opportunity_alerts=excluded.opportunity_alerts,product_updates=excluded.product_updates,marketing=excluded.marketing,onboarding_dismissed=excluded.onboarding_dismissed,updated_at=now() returning opportunity_alerts,product_updates,marketing,onboarding_dismissed,updated_at",(u['id'],vals['opportunity_alerts'],vals['product_updates'],vals['marketing'],vals['onboarding_dismissed']),'one');log_account_activity(u['id'],'preferences_updated','تم تحديث إعدادات الحساب',u.get('session_id'));return self.sendj(200,r)
            if p=='/api/v1/account/activity' and method=='GET':
                u=self.require();
                if not u:return
                return self.sendj(200,{'items':q("select id,event_type,label,meta,created_at from account_activity where user_id=%s order by created_at desc limit 60",(u['id'],))})
            if p=='/api/v1/onboarding' and method=='GET':
                u=self.require();
                if not u:return
                return self.sendj(200,onboarding_status(u['id'],u['role']))
            if p=='/api/v1/onboarding/dismiss' and method=='POST':
                u=self.require();
                if not u:return
                q("insert into user_preferences(user_id,onboarding_dismissed) values(%s,true) on conflict(user_id) do update set onboarding_dismissed=true,updated_at=now()",(u['id'],),None);return self.sendj(200,{'ok':True})
            if p=='/api/v1/legal/status' and method=='GET':
                u=self.require();
                if not u:return
                return self.sendj(200,legal_status(u['id']))
            if p=='/api/v1/legal/accept' and method=='POST':
                u=self.require();
                if not u:return
                b=self.body();docs=b.get('documents') if isinstance(b.get('documents'),list) else [];valid=legal_versions();accepted=[]
                for doc in docs:
                    if doc in valid:q("insert into legal_acceptances(user_id,document,version) values(%s,%s,%s) on conflict do nothing",(u['id'],doc,valid[doc]),None);accepted.append(doc)
                if accepted:log_account_activity(u['id'],'legal_acceptance','تمت الموافقة على المستندات القانونية الحالية',u.get('session_id'),{'documents':accepted})
                return self.sendj(200,legal_status(u['id']))
            if p=='/api/v1/account/sessions' and method=='GET':
                u=self.require();
                if not u:return
                items=q("select id,device_label,created_at,last_seen_at,expires_at from sessions where user_id=%s and revoked_at is null and expires_at>now() order by coalesce(last_seen_at,created_at) desc",(u['id'],))
                for x in items:x['current']=int(x['id'])==int(u.get('session_id') or 0)
                return self.sendj(200,{'items':items,'session_ttl_days':SESSION_TTL_DAYS})
            if p=='/api/v1/account/sessions/revoke-others' and method=='POST':
                u=self.require();
                if not u:return
                q('update sessions set revoked_at=now() where user_id=%s and id<>%s and revoked_at is null',(u['id'],u['session_id']),None)
                log_account_activity(u['id'],'sessions_revoked','تم تسجيل خروج الأجهزة الأخرى',u.get('session_id'))
                return self.sendj(200,{'ok':True})
            m=re.fullmatch(r'/api/v1/account/sessions/(\d+)',p)
            if m and method=='DELETE':
                u=self.require();
                if not u:return
                sid=int(m.group(1)); row=q('update sessions set revoked_at=now() where id=%s and user_id=%s and revoked_at is null returning id',(sid,u['id']),'one')
                if not row:return self.sendj(404,{'error':'session_not_found'})
                log_account_activity(u['id'],'session_revoked','تم إنهاء جلسة جهاز',u.get('session_id'),{'revoked_session_id':sid})
                return self.sendj(200,{'ok':True,'current_revoked':sid==int(u.get('session_id') or 0)})
            if method=='GET' and p=='/api/v1/me/roles':
                u=self.require();
                if not u:return
                roles=enabled_roles(u['id'])
                return self.sendj(200,{'active_role':u['role'],'roles':roles})
            if method=='PATCH' and p=='/api/v1/me/active-role':
                u=self.require();
                if not u:return
                if u['role']=='admin':return self.sendj(403,{'error':'admin_role_locked'})
                b=self.body(); role=str(b.get('role') or '')
                if role not in ('client','freelancer'):return self.sendj(400,{'error':'invalid_role'})
                q("insert into user_roles(user_id,role,enabled) values(%s,%s,true) on conflict(user_id,role) do update set enabled=true",(u['id'],role),None)
                if role=='freelancer':q("insert into freelancer_profiles(user_id) values(%s) on conflict(user_id) do nothing",(u['id'],),None)
                q('update users set role=%s where id=%s',(role,u['id']),None)
                log_account_activity(u['id'],'role_switched','تم تغيير الدور النشط',u.get('session_id'),{'role':role})
                user=q('select id,phone,name,role,is_verified from users where id=%s',(u['id'],),'one'); roles=enabled_roles(u['id']); user['roles']=roles
                return self.sendj(200,{'user':user,'roles':roles,'active_role':role})
            if method=='POST' and p=='/api/v1/freelancer/kyc/start':
                u=self.require('freelancer');
                if not u:return
                if KYC_MODE!='adapter' or not _https_url(KYC_START_URL):return self.sendj(503,{'error':'kyc_provider_not_configured'})
                fp=q('select * from freelancer_profiles where user_id=%s',(u['id'],),'one')
                if not fp:return self.sendj(404,{'error':'freelancer_profile_not_found'})
                if fp.get('kyc_status')=='approved':return self.sendj(200,{'ok':True,'already_verified':True})
                if fp.get('kyc_status')=='pending' and fp.get('kyc_verification_url') and fp.get('kyc_provider_reference'):
                    return self.sendj(200,{'ok':True,'verification_url':fp['kyc_verification_url'],'provider_reference':fp['kyc_provider_reference'],'reused':True})
                claim=q("update freelancer_profiles set kyc_started_at=now() where user_id=%s and kyc_status<>'approved' and (kyc_started_at is null or kyc_started_at<now()-interval '2 minutes') returning user_id",(u['id'],),'one')
                if not claim:return self.sendj(409,{'error':'kyc_initialization_in_progress','retry_after_seconds':120})
                payload={'user_id':u['id'],'phone':u.get('phone'),'name':u.get('name'),'return_url':(PUBLIC_BASE_URL+'/#account') if PUBLIC_BASE_URL else None,'webhook_contract':'minjaz-kyc-v1','webhook_url':(PUBLIC_BASE_URL+'/api/v1/integrations/kyc/webhook') if PUBLIC_BASE_URL else None}
                try:resp=adapter_post_json(KYC_START_URL,payload,KYC_ADAPTER_BEARER)
                except Exception as exc:
                    q('update freelancer_profiles set kyc_started_at=null where user_id=%s and kyc_provider_reference is null',(u['id'],),None);operational_event('error','kyc','provider_unavailable',repr(exc),self.request_id(),u.get('id'),'user',u.get('id'));print('KYC_ADAPTER_ERR',self.request_id(),repr(exc),flush=True);return self.sendj(502,{'error':'kyc_provider_unavailable'})
                verification_url=str(resp.get('verification_url') or '').strip(); provider_ref=str(resp.get('provider_reference') or '').strip()[:180]
                if not _https_url(verification_url) or not provider_ref:
                    q('update freelancer_profiles set kyc_started_at=null where user_id=%s and kyc_provider_reference is null',(u['id'],),None);return self.sendj(502,{'error':'invalid_kyc_provider_response'})
                q("update freelancer_profiles set kyc_status='pending',kyc_provider_reference=%s,kyc_verification_url=%s,kyc_started_at=null where user_id=%s",(provider_ref,verification_url,u['id']),None)
                return self.sendj(200,{'ok':True,'verification_url':verification_url,'provider_reference':provider_ref})
            if method=='PATCH' and p=='/api/v1/freelancer/profile':
                u=self.require('freelancer');
                if not u:return
                b=self.body(); bio=b.get('bio'); skills=b.get('skills') if isinstance(b.get('skills'),list) else None; avail=b.get('is_available') if 'is_available' in b else None
                q('update freelancer_profiles set bio=coalesce(%s,bio),skills=coalesce(%s::text[],skills),is_available=coalesce(%s,is_available) where user_id=%s',(None if bio is None else str(bio)[:500],skills,avail,u['id']),None)
                return self.sendj(200,q('select * from freelancer_profiles where user_id=%s',(u['id'],),'one'))
            if p=='/api/v1/client/profile':
                u=self.require('client');
                if not u:return
                if method=='GET':
                    prof=q('select user_id,company_name,bio,city,sector,updated_at from client_profiles where user_id=%s',(u['id'],),'one') or {'user_id':u['id'],'company_name':None,'bio':None,'city':None,'sector':None}
                    stats=q("select count(*)::int tasks_created,(select count(*)::int from orders where client_id=%s and status='completed') completed_orders from tasks where client_id=%s",(u['id'],u['id']),'one') or {}
                    return self.sendj(200,{**prof,'stats':stats})
                if method=='PATCH':
                    b=self.body();company=str(b.get('company_name') or '').strip()[:160] or None;bio=str(b.get('bio') or '').strip()[:1000] or None;city=str(b.get('city') or '').strip()[:120] or None;sector=str(b.get('sector') or '').strip()[:120] or None
                    r=q("""insert into client_profiles(user_id,company_name,bio,city,sector) values(%s,%s,%s,%s,%s)
                          on conflict(user_id) do update set company_name=excluded.company_name,bio=excluded.bio,city=excluded.city,sector=excluded.sector,updated_at=now()
                          returning user_id,company_name,bio,city,sector,updated_at""",(u['id'],company,bio,city,sector),'one')
                    return self.sendj(200,r)
            if method=='GET' and p=='/api/v1/freelancers':
                a=q("select us.id user_id,us.name,fp.bio,fp.skills,fp.rating,fp.completed_tasks,fp.on_time_rate,fp.avg_response_minutes,fp.is_available,fp.kyc_status from users us join freelancer_profiles fp on fp.user_id=us.id order by fp.rating desc,fp.completed_tasks desc limit 300")
                viewer=auth(self.headers)
                if viewer and viewer.get('role')=='client':a=[x for x in a if not interaction_restricted(viewer['id'],x['user_id'])]
                qtext=_match_text((query.get('q') or [''])[0]);skill=_match_text((query.get('skill') or [''])[0]);avail=(query.get('available') or [''])[0];verified=(query.get('verified') or [''])[0]
                if qtext:a=[x for x in a if qtext in _match_text(' '.join([str(x.get('name') or ''),str(x.get('bio') or ''),' '.join(x.get('skills') or [])]))]
                if skill:a=[x for x in a if any(skill in _match_text(v) for v in (x.get('skills') or []))]
                if avail=='1':a=[x for x in a if bool(x.get('is_available'))]
                if verified=='1':a=[x for x in a if x.get('kyc_status')=='approved']
                sort=(query.get('sort') or ['rating'])[0]
                if sort=='completed':a.sort(key=lambda x:(int(x.get('completed_tasks') or 0),float(x.get('rating') or 0)),reverse=True)
                elif sort=='response':a.sort(key=lambda x:(int(x.get('avg_response_minutes') or 999999),-float(x.get('rating') or 0)))
                else:a.sort(key=lambda x:(float(x.get('rating') or 0),int(x.get('completed_tasks') or 0)),reverse=True)
                try:limit=max(1,min(int((query.get('limit') or ['100'])[0]),200))
                except Exception:limit=100
                return self.sendj(200,{'items':a[:limit]})
            m=re.fullmatch(r'/api/v1/freelancers/(\d+)/public',p)
            if m and method=='GET':
                fid=int(m.group(1))
                fp=q("select us.id user_id,us.name,fp.bio,fp.skills,fp.rating,fp.completed_tasks,fp.on_time_rate,fp.avg_response_minutes,fp.is_available,fp.kyc_status from users us join freelancer_profiles fp on fp.user_id=us.id where us.id=%s",(fid,),'one')
                if not fp:return self.sendj(404,{'error':'freelancer_not_found'})
                fp['portfolio']=q('select id,title,description,external_url,created_at from freelancer_portfolio_items where freelancer_id=%s order by created_at desc limit 12',(fid,))
                fp['reviews']=q("select rv.quality,rv.timeliness,rv.communication,rv.comment,rv.created_at,coalesce(nullif(split_part(us.name,' ',1),''),'عميل') reviewer_name from reviews rv join users us on us.id=rv.reviewer_id where rv.reviewee_id=%s order by rv.created_at desc limit 12",(fid,))
                viewer=auth(self.headers)
                if viewer:
                    fp['blocked_by_me']=bool(q('select 1 from user_blocks where blocker_id=%s and blocked_id=%s',(viewer['id'],fid),'one'))
                    fp['interaction_restricted']=interaction_restricted(viewer['id'],fid)
                return self.sendj(200,fp)
            if p=='/api/v1/freelancer/portfolio':
                u=self.require('freelancer');
                if not u:return
                if method=='GET':return self.sendj(200,{'items':q('select id,title,description,external_url,created_at from freelancer_portfolio_items where freelancer_id=%s order by created_at desc limit 20',(u['id'],))})
                if method=='POST':
                    b=self.body();title=str(b.get('title') or '').strip();desc=str(b.get('description') or '').strip();url=str(b.get('external_url') or '').strip()
                    if len(title)<3:return self.sendj(400,{'error':'invalid_title'})
                    if url and not url.startswith('https://'):return self.sendj(400,{'error':'https_url_required'})
                    n=q('select count(*)::int n from freelancer_portfolio_items where freelancer_id=%s',(u['id'],),'one')['n']
                    if n>=12:return self.sendj(409,{'error':'portfolio_limit'})
                    r=q('insert into freelancer_portfolio_items(freelancer_id,title,description,external_url) values(%s,%s,%s,%s) returning id,title,description,external_url,created_at',(u['id'],title[:160],desc[:1500] or None,url[:1000] or None),'one');return self.sendj(201,r)
            m=re.fullmatch(r'/api/v1/freelancer/portfolio/(\d+)',p)
            if m and method=='DELETE':
                u=self.require('freelancer');
                if not u:return
                q('delete from freelancer_portfolio_items where id=%s and freelancer_id=%s',(int(m.group(1)),u['id']),None);return self.sendj(200,{'ok':True})
            m=re.fullmatch(r'/api/v1/freelancers/(\d+)/invite',p)
            if m and method=='POST':
                u=self.require('client');
                if not u:return
                fid=int(m.group(1));b=self.body();tid=int(b.get('task_id') or 0)
                fp=q('select user_id from freelancer_profiles where user_id=%s',(fid,),'one')
                if not fp:return self.sendj(404,{'error':'freelancer_not_found'})
                if interaction_restricted(u['id'],fid):return self.sendj(403,{'error':'interaction_restricted'})
                t=q("select id,title from tasks where id=%s and client_id=%s and status='open'",(tid,u['id']),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                if task_hidden(tid):return self.sendj(403,{'error':'task_hidden'})
                note=str(b.get('note') or '').strip()[:500] or None
                r=q("insert into task_invitations(task_id,client_id,freelancer_id,note) values(%s,%s,%s,%s) on conflict(task_id,freelancer_id) do update set note=excluded.note,status='sent',updated_at=now() returning *",(tid,u['id'],fid,note),'one')
                notify(fid,'دعوة خاصة لمهمة',t['title']+((' · '+note) if note else ''),'task_invite',None,tid)
                return self.sendj(201,r)
            if p=='/api/v1/freelancer/earnings' and method=='GET':
                u=self.require('freelancer');
                if not u:return
                bal=freelancer_earnings(u['id'])
                bal['payout_requests']=q("select id,amount,status,note,admin_note,created_at,updated_at,resolved_at from payout_requests where freelancer_id=%s order by created_at desc limit 100",(u['id'],))
                return self.sendj(200,bal)
            if p=='/api/v1/freelancer/payouts':
                u=self.require('freelancer');
                if not u:return
                if method=='GET':
                    return self.sendj(200,{'items':q("select id,amount,status,note,admin_note,created_at,updated_at,resolved_at from payout_requests where freelancer_id=%s order by created_at desc limit 100",(u['id'],)),'balance':freelancer_earnings(u['id'])})
                if method=='POST':
                    b=self.body();r,err,available=create_payout_request(u['id'],b.get('amount'),b.get('note'))
                    if err=='kyc_required':return self.sendj(403,{'error':err})
                    if err=='insufficient_balance':return self.sendj(409,{'error':err,'available_balance':float(available)})
                    if err:return self.sendj(400,{'error':err})
                    notify(u['id'],'تم استلام طلب السحب',f"المبلغ {float(r['amount']):.2f} ر.س قيد المراجعة",'payout',None)
                    return self.sendj(201,{'item':r,'balance':freelancer_earnings(u['id'])})
            if p=='/api/v1/freelancer/favorite-tasks' and method=='GET':
                u=self.require('freelancer');
                if not u:return
                return self.sendj(200,{'items':q("select ft.task_id,ft.created_at,t.title,t.description,t.status,t.budget_min,t.budget_max,t.urgency,c.name_ar category_name from favorite_tasks ft join tasks t on t.id=ft.task_id left join categories c on c.id=t.category_id where ft.freelancer_id=%s and not exists(select 1 from task_moderation tm where tm.task_id=t.id and tm.hidden=true) and not exists(select 1 from user_blocks ub where (ub.blocker_id=%s and ub.blocked_id=t.client_id) or (ub.blocker_id=t.client_id and ub.blocked_id=%s)) and not exists(select 1 from user_moderation um where um.interaction_restricted=true and um.user_id in (%s,t.client_id)) order by ft.created_at desc",(u['id'],u['id'],u['id'],u['id']))})
            m=re.fullmatch(r'/api/v1/freelancer/favorite-tasks/(\d+)',p)
            if m:
                u=self.require('freelancer');
                if not u:return
                tid=int(m.group(1));t=q('select id,status,client_id from tasks where id=%s',(tid,),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                if int(t['client_id'])==int(u['id']):return self.sendj(403,{'error':'own_task_forbidden'})
                if method=='POST' and (task_hidden(tid) or interaction_restricted(u['id'],t['client_id'])):return self.sendj(403,{'error':'interaction_restricted'})
                if method=='POST':q('insert into favorite_tasks(freelancer_id,task_id) values(%s,%s) on conflict do nothing',(u['id'],tid),None);return self.sendj(201,{'ok':True,'task_id':tid})
                if method=='DELETE':q('delete from favorite_tasks where freelancer_id=%s and task_id=%s',(u['id'],tid),None);return self.sendj(200,{'ok':True,'task_id':tid})
            if p=='/api/v1/freelancer/saved-searches':
                u=self.require('freelancer');
                if not u:return
                if method=='GET':return self.sendj(200,{'items':q('select id,name,filters,created_at,updated_at from saved_task_searches where freelancer_id=%s order by created_at desc limit 20',(u['id'],))})
                if method=='POST':
                    b=self.body();name=str(b.get('name') or '').strip()[:80];filters=b.get('filters') if isinstance(b.get('filters'),dict) else {}
                    if not name:return self.sendj(400,{'error':'name_required'})
                    allowed={'q','category_id','urgency','proposal','min_budget','sort'};clean={k:str(v)[:160] for k,v in filters.items() if k in allowed and str(v).strip()}
                    if len(clean)>8:return self.sendj(400,{'error':'invalid_filters'})
                    r=q('insert into saved_task_searches(freelancer_id,name,filters) values(%s,%s,%s::jsonb) returning id,name,filters,created_at,updated_at',(u['id'],name,json.dumps(clean,ensure_ascii=False)),'one');return self.sendj(201,r)
            m=re.fullmatch(r'/api/v1/freelancer/saved-searches/(\d+)',p)
            if m and method=='DELETE':
                u=self.require('freelancer');
                if not u:return
                q('delete from saved_task_searches where id=%s and freelancer_id=%s',(int(m.group(1)),u['id']),None);return self.sendj(200,{'ok':True})
            if p=='/api/v1/tasks' and method=='GET':
                u=self.require();
                if not u:return
                if u['role']=='client':
                    a=q("select t.*,c.name_ar category_name,(select count(*)::int from proposals p where p.task_id=t.id) proposal_count from tasks t left join categories c on c.id=t.category_id where t.client_id=%s order by t.created_at desc limit 200",(u['id'],))
                elif u['role']=='freelancer':
                    a=q("""select t.*,c.name_ar category_name,c.slug category_slug,s.name_ar service_name,
                                 exists(select 1 from proposals p where p.task_id=t.id and p.freelancer_id=%s) has_proposal,
                                 exists(select 1 from task_invitations ti where ti.task_id=t.id and ti.freelancer_id=%s and ti.status in ('sent','viewed')) invited,
                                 exists(select 1 from favorite_tasks ft where ft.task_id=t.id and ft.freelancer_id=%s) favorited
                          from tasks t
                          left join categories c on c.id=t.category_id
                          left join services s on s.id=t.service_id
                          where t.status='open' and t.client_id<>%s
                            and not exists(select 1 from user_blocks ub where (ub.blocker_id=%s and ub.blocked_id=t.client_id) or (ub.blocker_id=t.client_id and ub.blocked_id=%s))
                            and not exists(select 1 from user_moderation um where um.interaction_restricted=true and um.user_id in (%s,t.client_id))
                            and not exists(select 1 from task_moderation tm where tm.task_id=t.id and tm.hidden=true)
                          order by t.created_at desc limit 300""",(u['id'],u['id'],u['id'],u['id'],u['id'],u['id'],u['id']))
                    prof=q('select skills from freelancer_profiles where user_id=%s',(u['id'],),'one') or {}
                    skills=prof.get('skills') or []
                    for item in a:
                        score,matched=opportunity_relevance(item,skills)
                        item['match_score']=score; item['matched_skills']=matched
                    qtext=_match_text((query.get('q') or [''])[0])
                    cat_raw=(query.get('category_id') or [''])[0]
                    urgency=(query.get('urgency') or [''])[0]
                    bid=(query.get('proposal') or [''])[0]
                    try: cat_id=int(cat_raw) if cat_raw else None
                    except Exception: cat_id=None
                    try: min_budget=float((query.get('min_budget') or [''])[0]) if (query.get('min_budget') or [''])[0] else None
                    except Exception: min_budget=None
                    if qtext:
                        a=[x for x in a if qtext in _match_text(' '.join([str(x.get('title') or ''),str(x.get('description') or ''),str(x.get('category_name') or ''),str(x.get('service_name') or '')]))]
                    if cat_id is not None:a=[x for x in a if int(x.get('category_id') or 0)==cat_id]
                    if urgency in ('normal','urgent'):a=[x for x in a if x.get('urgency')==urgency]
                    if bid=='sent':a=[x for x in a if bool(x.get('has_proposal'))]
                    elif bid=='new':a=[x for x in a if not bool(x.get('has_proposal'))]
                    if min_budget is not None:
                        a=[x for x in a if float(x.get('budget_max') or x.get('budget_min') or 0)>=min_budget]
                    sort=(query.get('sort') or ['match'])[0]
                    if sort=='budget_desc':a.sort(key=lambda x:float(x.get('budget_max') or x.get('budget_min') or 0),reverse=True)
                    elif sort=='latest':a.sort(key=lambda x:str(x.get('created_at') or ''),reverse=True)
                    else:a.sort(key=lambda x:(int(x.get('match_score') or 0),str(x.get('created_at') or '')),reverse=True)
                    try: limit=max(1,min(int((query.get('limit') or ['200'])[0]),200))
                    except Exception: limit=200
                    a=a[:limit]
                else:
                    a=q('select t.*,c.name_ar category_name from tasks t left join categories c on c.id=t.category_id order by t.created_at desc limit 300')
                return self.sendj(200,{'items':a})
            if p=='/api/v1/tasks' and method=='POST':
                u=self.require('client');
                if not u:return
                if q("select count(*)::int n from tasks where client_id=%s and created_at>now()-interval '1 hour'",(u['id'],),'one')['n']>=20:return self.sendj(429,{'error':'task_rate_limited','retry_after_seconds':3600})
                b=self.body(); title=str(b.get('title','')).strip(); desc=str(b.get('description','')).strip()
                if not title or not desc:return self.sendj(400,{'error':'missing_fields'})
                if len(title)<5:return self.sendj(400,{'error':'title_too_short','minimum':5})
                if len(title)>180:return self.sendj(400,{'error':'title_too_long','maximum':180})
                if len(desc)<20:return self.sendj(400,{'error':'description_too_short','minimum':20})
                if len(desc)>6000:return self.sendj(400,{'error':'description_too_long','maximum':6000})
                sid=b.get('service_id') or None; category_id=b.get('category_id') or None
                if sid:
                    svc=q('select id,category_id from services where id=%s and active=true',(sid,),'one')
                    if not svc:return self.sendj(400,{'error':'invalid_service'})
                    category_id=svc['category_id']; sid=svc['id']
                else:
                    try: category_id=int(category_id)
                    except Exception:return self.sendj(400,{'error':'invalid_category'})
                    if not q('select 1 from categories where id=%s and is_active=true',(category_id,),'one'):return self.sendj(400,{'error':'invalid_category'})
                urgency=str(b.get('urgency') or 'normal').strip().lower()
                if urgency not in ('normal','urgent'):return self.sendj(400,{'error':'invalid_urgency'})
                try:
                    bmin=float(b.get('budget_min')) if b.get('budget_min') not in (None,'') else None; bmax=float(b.get('budget_max')) if b.get('budget_max') not in (None,'') else None
                except Exception:return self.sendj(400,{'error':'invalid_budget'})
                if (bmin is not None and bmin<49) or (bmax is not None and bmax<49):return self.sendj(400,{'error':'budget_below_minimum','minimum':49})
                if (bmin is not None and bmin>1_000_000) or (bmax is not None and bmax>1_000_000):return self.sendj(400,{'error':'budget_above_maximum','maximum':1000000})
                if bmin is not None and bmax is not None and bmax<bmin:return self.sendj(400,{'error':'invalid_budget_range'})
                due_raw=str(b.get('due_at') or '').strip() or None
                if due_raw:
                    try:
                        due_dt=datetime.fromisoformat(due_raw.replace('Z','+00:00'))
                        now_dt=datetime.now(due_dt.tzinfo) if due_dt.tzinfo else datetime.now()
                        if due_dt<=now_dt:return self.sendj(400,{'error':'due_at_must_be_future'})
                    except (ValueError,TypeError):return self.sendj(400,{'error':'invalid_due_at'})
                r=q("insert into tasks(client_id,category_id,service_id,title,description,budget_min,budget_max,urgency,due_at,status) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,'open') returning *",(u['id'],category_id,sid,title,desc,bmin,bmax,urgency,due_raw),'one'); insert_attachments(u['id'],b.get('attachments'),task_id=r['id']); return self.sendj(201,r)
            m=re.fullmatch(r'/api/v1/tasks/(\d+)',p)
            if m and method=='GET':
                u=self.require();
                if not u:return
                tid=int(m.group(1));t=q("""select t.*,c.name_ar category_name,c.slug category_slug,s.name_ar service_name,cu.name client_name,cu.created_at client_joined_at,
                    (select count(*)::int from tasks tx where tx.client_id=t.client_id) client_tasks_count,
                    (select count(*)::int from orders ox where ox.client_id=t.client_id and ox.status='completed') client_completed_orders,
                    cp.company_name client_company,cp.city client_city,cp.sector client_sector
                    from tasks t left join categories c on c.id=t.category_id left join services s on s.id=t.service_id join users cu on cu.id=t.client_id left join client_profiles cp on cp.user_id=t.client_id where t.id=%s""",(tid,),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                if u['role']=='client' and int(t['client_id'])!=int(u['id']):return self.sendj(403,{'error':'forbidden'})
                if u['role']=='freelancer':
                    shared=q('select 1 from orders where task_id=%s and freelancer_id=%s',(tid,u['id']),'one')
                    if t.get('status')!='open' and not shared:return self.sendj(403,{'error':'forbidden'})
                    if not shared and (task_hidden(tid) or interaction_restricted(u['id'],t['client_id'])):return self.sendj(403,{'error':'interaction_restricted'})
                    t['has_proposal']=bool(q('select 1 from proposals where task_id=%s and freelancer_id=%s',(tid,u['id']),'one'))
                    t['client_blocked_by_me']=bool(q('select 1 from user_blocks where blocker_id=%s and blocked_id=%s',(u['id'],t['client_id']),'one'))
                    t['invited']=bool(q("select 1 from task_invitations where task_id=%s and freelancer_id=%s and status in ('sent','viewed')",(tid,u['id']),'one'))
                    t['favorited']=bool(q('select 1 from favorite_tasks where task_id=%s and freelancer_id=%s',(tid,u['id']),'one'))
                    if t['invited']:q("update task_invitations set status='viewed',updated_at=now() where task_id=%s and freelancer_id=%s and status='sent'",(tid,u['id']),None)
                    t['proposal']=q('select id,price,delivery_hours,revisions,message,status,created_at from proposals where task_id=%s and freelancer_id=%s',(tid,u['id']),'one')
                t['attachments']=public_attachments(q('select id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode,created_at from attachments where task_id=%s order by created_at',(tid,)))
                return self.sendj(200,t)
            m=re.fullmatch(r'/api/v1/tasks/(\d+)/attachments',p)
            if m and method=='GET':
                u=self.require();
                if not u:return
                tid=int(m.group(1));t=q('select client_id,status from tasks where id=%s',(tid,),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                if u['role']=='client' and int(t['client_id'])!=int(u['id']):return self.sendj(403,{'error':'forbidden'})
                if u['role']=='freelancer' and t.get('status')!='open':
                    ok=q('select 1 from orders where task_id=%s and freelancer_id=%s',(tid,u['id']),'one')
                    if not ok:return self.sendj(403,{'error':'forbidden'})
                return self.sendj(200,{'items':public_attachments(q('select id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode,created_at from attachments where task_id=%s order by created_at',(tid,)))})
            m=re.fullmatch(r'/api/v1/tasks/(\d+)/repeat',p)
            if m and method=='POST':
                u=self.require('client');
                if not u:return
                t=q('select * from tasks where id=%s and client_id=%s',(int(m.group(1)),u['id']),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                r=q("insert into tasks(client_id,category_id,service_id,title,description,budget_min,budget_max,urgency,status) values(%s,%s,%s,%s,%s,%s,%s,%s,'open') returning *",(u['id'],t.get('category_id'),t.get('service_id'),t['title'],t['description'],t.get('budget_min'),t.get('budget_max'),t.get('urgency') or 'normal'),'one');return self.sendj(201,r)
            m=re.fullmatch(r'/api/v1/tasks/(\d+)/proposals',p)
            if m and method=='POST':
                u=self.require('freelancer');
                if not u:return
                if q("select count(*)::int n from proposals where freelancer_id=%s and created_at>now()-interval '1 hour'",(u['id'],),'one')['n']>=40:return self.sendj(429,{'error':'proposal_rate_limited','retry_after_seconds':3600})
                b=self.body()
                try: price=float(b.get('price') or 0)
                except Exception:return self.sendj(400,{'error':'invalid_price'})
                if price<=0:return self.sendj(400,{'error':'invalid_price'})
                if price>1_000_000:return self.sendj(400,{'error':'price_above_maximum','maximum':1000000})
                try: delivery_hours=int(b.get('delivery_hours') or 24); revisions=int(b.get('revisions') if b.get('revisions') not in (None,'') else 1)
                except Exception:return self.sendj(400,{'error':'invalid_proposal_terms'})
                if delivery_hours<1 or delivery_hours>8760:return self.sendj(400,{'error':'invalid_delivery_hours','minimum':1,'maximum':8760})
                if revisions<0 or revisions>50:return self.sendj(400,{'error':'invalid_revisions','minimum':0,'maximum':50})
                message=str(b.get('message') or '').strip()
                if len(message)>1200:return self.sendj(400,{'error':'proposal_message_too_long','maximum':1200})
                t=q("select id,client_id from tasks where id=%s and status='open'",(int(m.group(1)),),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                if int(t['client_id'])==int(u['id']):return self.sendj(403,{'error':'own_task_forbidden'})
                if task_hidden(int(m.group(1))) or interaction_restricted(u['id'],t['client_id']):return self.sendj(403,{'error':'interaction_restricted'})
                r=q("insert into proposals(task_id,freelancer_id,price,delivery_hours,revisions,message) values(%s,%s,%s,%s,%s,%s) on conflict(task_id,freelancer_id) do update set price=excluded.price,delivery_hours=excluded.delivery_hours,revisions=excluded.revisions,message=excluded.message returning *",(int(m.group(1)),u['id'],price,delivery_hours,revisions,message or None),'one');notify(t['client_id'],'عرض جديد على مهمتك',f"السعر {price:.2f} ر.س · التسليم خلال {delivery_hours} ساعة",'proposal',None,int(m.group(1)));return self.sendj(201,r)
            if m and method=='GET':
                u=self.require();
                if not u:return
                t=q('select * from tasks where id=%s',(int(m.group(1)),),'one')
                if not t:return self.sendj(404,{'error':'task_not_found'})
                if u['role']=='client' and int(t['client_id'])!=int(u['id']):return self.sendj(403,{'error':'forbidden'})
                if u['role']=='freelancer':
                    a=q("select p.*,us.name,fp.bio,fp.skills,fp.rating,fp.completed_tasks,fp.on_time_rate,fp.avg_response_minutes,fp.is_available,fp.kyc_status from proposals p join users us on us.id=p.freelancer_id left join freelancer_profiles fp on fp.user_id=p.freelancer_id where p.task_id=%s and p.freelancer_id=%s order by p.created_at",(int(m.group(1)),u['id']))
                else:
                    a=q("select p.*,us.name,fp.bio,fp.skills,fp.rating,fp.completed_tasks,fp.on_time_rate,fp.avg_response_minutes,fp.is_available,fp.kyc_status from proposals p join users us on us.id=p.freelancer_id left join freelancer_profiles fp on fp.user_id=p.freelancer_id where p.task_id=%s order by p.created_at",(int(m.group(1)),))
                return self.sendj(200,{'items':a})
            if p=='/api/v1/orders' and method=='POST':
                u=self.require('client');
                if not u:return
                b=self.body(); x=q("select p.*,t.client_id,t.id task_id from proposals p join tasks t on t.id=p.task_id where p.id=%s and p.status='sent' and t.status='open'",(b.get('proposal_id'),),'one')
                if not x or int(x['client_id'])!=int(u['id']):return self.sendj(404,{'error':'proposal_not_found'})
                if task_hidden(x['task_id']) or interaction_restricted(u['id'],x['freelancer_id']):return self.sendj(403,{'error':'interaction_restricted'})
                ex=q('select id from orders where task_id=%s',(x['task_id'],),'one')
                if ex:return self.sendj(409,{'error':'order_exists'})
                fee=round(float(x['price'])*float(FEE)/100,2); r=q("insert into orders(task_id,proposal_id,client_id,freelancer_id,amount,platform_fee,status,payment_status) values(%s,%s,%s,%s,%s,%s,'awaiting_payment','unpaid') returning *",(x['task_id'],x['id'],u['id'],x['freelancer_id'],x['price'],fee),'one');q("update proposals set status=case when id=%s then 'accepted' else 'rejected' end where task_id=%s",(x['id'],x['task_id']),None);q("update tasks set status='matched',updated_at=now() where id=%s",(x['task_id'],),None);notify(x['freelancer_id'],'تم اختيار عرضك','بانتظار دفع العميل لبدء التنفيذ','order',r['id']);return self.sendj(201,r)
            if p=='/api/v1/orders' and method=='GET':
                u=self.require();
                if not u:return
                col='client_id' if u['role']=='client' else 'freelancer_id'
                a=q(f"""select o.*,t.title,t.description,t.due_at,t.urgency,c.name client_name,f.name freelancer_name,
                    coalesce(p.delivery_hours,0) promised_hours,coalesce(p.revisions,0) revisions_allowed,
                    (select count(*)::int from order_revision_requests rr where rr.order_id=o.id) revisions_used,
                    greatest(coalesce(p.revisions,0)-(select count(*)::int from order_revision_requests rr where rr.order_id=o.id),0) revisions_remaining,
                    (o.amount-o.platform_fee) net_amount,exists(select 1 from reviews rv where rv.order_id=o.id) reviewed
                    from orders o join tasks t on t.id=o.task_id join users c on c.id=o.client_id join users f on f.id=o.freelancer_id
                    left join proposals p on p.id=o.proposal_id where o.{col}=%s order by o.created_at desc""",(u['id'],));return self.sendj(200,{'items':a})
            m=re.fullmatch(r'/api/v1/orders/(\d+)',p)
            if m and method=='GET':
                u=self.require();
                if not u:return
                o=q("select o.*,t.title,t.description,t.due_at,t.urgency,c.name client_name,f.name freelancer_name,coalesce(p.delivery_hours,0) promised_hours,coalesce(p.revisions,0) revisions_allowed,(select count(*)::int from order_revision_requests rr where rr.order_id=o.id) revisions_used,greatest(coalesce(p.revisions,0)-(select count(*)::int from order_revision_requests rr where rr.order_id=o.id),0) revisions_remaining,(o.amount-o.platform_fee) net_amount,rv.id review_id,rv.quality review_quality,rv.timeliness review_timeliness,rv.communication review_communication,rv.comment review_comment,rv.created_at review_created_at from orders o join tasks t on t.id=o.task_id join users c on c.id=o.client_id join users f on f.id=o.freelancer_id left join proposals p on p.id=o.proposal_id left join reviews rv on rv.order_id=o.id where o.id=%s and (o.client_id=%s or o.freelancer_id=%s)",(int(m.group(1)),u['id'],u['id']),'one');return self.sendj(404,{'error':'order_not_found'}) if not o else self.sendj(200,o)
            m=re.fullmatch(r'/api/v1/orders/(\d+)/(pay|deliver|revision|complete|review)',p)
            if m and method=='POST':
                oid=int(m.group(1)); action=m.group(2); u=self.require();
                if not u:return
                o=q('select * from orders where id=%s',(oid,),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                if action=='pay':
                    if u['role']!='client' or int(o['client_id'])!=int(u['id']):return self.sendj(403,{'error':'client_only'})
                    if o.get('payment_status')=='paid':return self.sendj(200,{'ok':True,'already_paid':True})
                    if o.get('status')!='awaiting_payment':return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    if PAYMENT_MODE=='mock':
                        if IS_PROD:return self.sendj(503,{'error':'mock_payment_disabled'})
                        q("update orders set payment_status='paid',status='in_progress' where id=%s",(oid,),None);q("update tasks set status='in_progress',updated_at=now() where id=%s",(o['task_id'],),None);log_order_event(oid,'payment','تم الدفع التجريبي',u['id'],meta={'mode':'mock'});notify(o['freelancer_id'],'تم دفع الطلب','تقدر تبدأ التنفيذ الآن','payment',oid);return self.sendj(200,{'ok':True,'mode':'mock'})
                    if PAYMENT_MODE!='adapter' or not _https_url(PAYMENT_CREATE_URL):return self.sendj(503,{'error':'payment_provider_not_configured'})
                    if o.get('payment_checkout_url') and o.get('provider_payment_id'):
                        return self.sendj(200,{'ok':True,'mode':'adapter','checkout_url':o['payment_checkout_url'],'provider_payment_id':o['provider_payment_id'],'reused':True})
                    claim=q("update orders set payment_checkout_started_at=now() where id=%s and payment_status='unpaid' and status='awaiting_payment' and (payment_checkout_started_at is null or payment_checkout_started_at<now()-interval '2 minutes') returning id",(oid,),'one')
                    if not claim:
                        latest=q('select payment_checkout_url,provider_payment_id from orders where id=%s',(oid,),'one') or {}
                        if latest.get('payment_checkout_url') and latest.get('provider_payment_id'):return self.sendj(200,{'ok':True,'mode':'adapter','checkout_url':latest['payment_checkout_url'],'provider_payment_id':latest['provider_payment_id'],'reused':True})
                        return self.sendj(409,{'error':'payment_initialization_in_progress','retry_after_seconds':120})
                    customer=q('select phone,name from users where id=%s',(u['id'],),'one') or {}
                    payload={'order_id':oid,'amount':float(o['amount']),'currency':'SAR','customer':{'phone':customer.get('phone'),'name':customer.get('name')},'return_url':(PUBLIC_BASE_URL+'/#orders') if PUBLIC_BASE_URL else None,'webhook_contract':'minjaz-normalized-v1','webhook_url':(PUBLIC_BASE_URL+'/api/v1/integrations/payments/webhook') if PUBLIC_BASE_URL else None}
                    try:resp=adapter_post_json(PAYMENT_CREATE_URL,payload,PAYMENT_ADAPTER_BEARER)
                    except Exception as exc:
                        q("update orders set payment_checkout_started_at=null where id=%s and payment_status='unpaid' and provider_payment_id is null",(oid,),None);operational_event('error','payment','provider_unavailable',repr(exc),self.request_id(),u.get('id'),'order',oid);print('PAYMENT_ADAPTER_ERR',self.request_id(),repr(exc),flush=True);return self.sendj(502,{'error':'payment_provider_unavailable'})
                    checkout=str(resp.get('checkout_url') or '').strip(); provider_id=str(resp.get('provider_payment_id') or '').strip()[:180]
                    if not _https_url(checkout) or not provider_id:
                        q("update orders set payment_checkout_started_at=null where id=%s and payment_status='unpaid' and provider_payment_id is null",(oid,),None);return self.sendj(502,{'error':'invalid_payment_provider_response'})
                    q("update orders set provider_payment_id=%s,payment_checkout_url=%s,payment_checkout_started_at=null where id=%s and payment_status='unpaid'",(provider_id,checkout,oid),None);log_order_event(oid,'payment_checkout','تم إنشاء رابط الدفع',u['id'],meta={'mode':'adapter'});return self.sendj(200,{'ok':True,'mode':'adapter','checkout_url':checkout,'provider_payment_id':provider_id})
                if action=='deliver':
                    if u['role']!='freelancer' or int(o['freelancer_id'])!=int(u['id']):return self.sendj(403,{'error':'freelancer_only'})
                    if o.get('payment_status')!='paid' or o.get('status') not in ('in_progress','revision_requested'):return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    b=self.body(); note=str(b.get('note') or '').strip()
                    if not note:return self.sendj(400,{'error':'note_required'})
                    d=q('insert into deliveries(order_id,freelancer_id,note) values(%s,%s,%s) returning *',(oid,u['id'],note[:5000]),'one'); insert_attachments(u['id'],b.get('attachments'),order_id=oid,delivery_id=d['id']); q("update order_revision_requests set status='satisfied',satisfied_at=now() where id=(select id from order_revision_requests where order_id=%s and status='open' order by sequence_no desc limit 1)",(oid,),None); q("update orders set status='delivered' where id=%s",(oid,),None);q("update tasks set status='delivered',updated_at=now() where id=%s",(o['task_id'],),None);notify(o['client_id'],'وصل تسليم جديد',note[:220],'delivery',oid);return self.sendj(201,{'ok':True,'delivery':d})
                if action=='revision':
                    if u['role']!='client' or int(o['client_id'])!=int(u['id']):return self.sendj(403,{'error':'client_only'})
                    if o.get('status')!='delivered':return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    b=self.body(); note=str(b.get('note') or '').strip()
                    if not note:return self.sendj(400,{'error':'note_required'})
                    lim=q('select coalesce(p.revisions,0)::int allowed,(select count(*)::int from order_revision_requests rr where rr.order_id=o.id) used from orders o left join proposals p on p.id=o.proposal_id where o.id=%s',(oid,),'one')
                    allowed=int(lim.get('allowed') or 0); used=int(lim.get('used') or 0)
                    if used>=allowed:return self.sendj(409,{'error':'revision_limit_reached','allowed':allowed,'used':used})
                    rr=q("insert into order_revision_requests(order_id,requested_by,sequence_no,note) values(%s,%s,%s,%s) returning *",(oid,u['id'],used+1,note[:3000]),'one')
                    q("insert into messages(order_id,sender_id,body) values(%s,%s,%s)",(oid,u['id'],('طلب تعديل '+str(used+1)+'/'+str(allowed)+': '+note)[:4000]),None)
                    q("update orders set status='revision_requested' where id=%s",(oid,),None);q("update tasks set status='in_progress',updated_at=now() where id=%s",(o['task_id'],),None);notify(o['freelancer_id'],'طلب تعديل جديد',note[:220],'revision',oid);return self.sendj(200,{'ok':True,'revision':rr,'remaining':max(allowed-(used+1),0)})
                if action=='complete':
                    if u['role']!='client' or int(o['client_id'])!=int(u['id']):return self.sendj(403,{'error':'client_only'})
                    if o.get('payment_status')!='paid' or o.get('status')!='delivered':return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    q("update orders set status='completed',completed_at=now() where id=%s",(oid,),None);q("update tasks set status='completed',updated_at=now() where id=%s",(o['task_id'],),None);refresh_freelancer(o['freelancer_id']);notify(o['freelancer_id'],'تم إكمال الطلب','اعتمد العميل التسليم','completed',oid);return self.sendj(200,{'ok':True})
                if action=='review':
                    if u['role']!='client' or int(o['client_id'])!=int(u['id']):return self.sendj(403,{'error':'client_only'})
                    if o.get('status')!='completed':return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    b=self.body(); vals=[int(b.get(k) or 0) for k in ('quality','timeliness','communication')]
                    if any(x<1 or x>5 for x in vals):return self.sendj(400,{'error':'invalid_rating'})
                    q("insert into reviews(order_id,reviewer_id,reviewee_id,quality,timeliness,communication,comment) values(%s,%s,%s,%s,%s,%s,%s) on conflict(order_id) do update set quality=excluded.quality,timeliness=excluded.timeliness,communication=excluded.communication,comment=excluded.comment",(oid,u['id'],o['freelancer_id'],*vals,str(b.get('comment') or '')[:2000] or None),None);refresh_freelancer(o['freelancer_id']);notify(o['freelancer_id'],'وصلك تقييم جديد',str(b.get('comment') or 'تم تحديث تقييمك')[:220],'review',oid);return self.sendj(201,{'ok':True})
            m=re.fullmatch(r'/api/v1/orders/(\d+)/dispute',p)
            if m:
                u=self.require()
                if not u:return
                oid=int(m.group(1))
                o=q('select o.*,t.status task_status from orders o join tasks t on t.id=o.task_id where o.id=%s and (o.client_id=%s or o.freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                if method=='GET':
                    return self.sendj(200,{'item':q('select d.*,us.name opened_by_name from order_disputes d join users us on us.id=d.opened_by where d.order_id=%s order by d.created_at desc limit 1',(oid,),'one')})
                if method=='POST':
                    if o.get('status') in ('completed','cancelled'):return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    active=q("select id from order_disputes where order_id=%s and status in ('open','in_review') order by created_at desc limit 1",(oid,),'one')
                    if active:return self.sendj(409,{'error':'active_dispute_exists','id':active['id']})
                    b=self.body();reason=str(b.get('reason') or '').strip();details=str(b.get('details') or '').strip()
                    if len(reason)<3:return self.sendj(400,{'error':'reason_required'})
                    d=q("insert into order_disputes(order_id,opened_by,reason,details,previous_order_status,previous_task_status) values(%s,%s,%s,%s,%s,%s) returning *",(oid,u['id'],reason[:180],details[:4000] or None,o.get('status'),o.get('task_status')),'one')
                    q("update orders set status='disputed' where id=%s",(oid,),None);q("update tasks set status='disputed',updated_at=now() where id=%s",(o['task_id'],),None)
                    other=o['freelancer_id'] if int(u['id'])==int(o['client_id']) else o['client_id'];notify(other,'تم فتح نزاع على الطلب',reason[:220],'dispute',oid);notify_admins('نزاع جديد يحتاج مراجعة',reason[:220],'dispute',oid)
                    return self.sendj(201,d)
            m=re.fullmatch(r'/api/v1/orders/(\d+)/cancellation',p)
            if m:
                u=self.require()
                if not u:return
                oid=int(m.group(1))
                o=q('select o.*,t.status task_status,t.title from orders o join tasks t on t.id=o.task_id where o.id=%s and (o.client_id=%s or o.freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                if method=='GET':
                    return self.sendj(200,{'item':q('select cr.*,us.name requested_by_name from order_cancellation_requests cr join users us on us.id=cr.requested_by where cr.order_id=%s order by cr.created_at desc limit 1',(oid,),'one')})
                if method=='POST':
                    if o.get('status') in ('completed','cancelled','disputed'):return self.sendj(409,{'error':'invalid_order_state','state':o.get('status')})
                    active=q("select id from order_cancellation_requests where order_id=%s and status in ('pending','in_review') order by created_at desc limit 1",(oid,),'one')
                    if active:return self.sendj(409,{'error':'active_cancellation_exists','id':active['id']})
                    b=self.body();reason=str(b.get('reason') or '').strip();details=str(b.get('details') or '').strip()
                    if len(reason)<3:return self.sendj(400,{'error':'reason_required'})
                    refund='pending' if o.get('payment_status')=='paid' else 'not_needed'
                    cr=q("insert into order_cancellation_requests(order_id,requested_by,reason,details,previous_order_status,previous_task_status,payment_status_at_request,refund_status) values(%s,%s,%s,%s,%s,%s,%s,%s) returning *",(oid,u['id'],reason[:180],details[:4000] or None,o.get('status'),o.get('task_status'),o.get('payment_status'),refund),'one')
                    other=o['freelancer_id'] if int(u['id'])==int(o['client_id']) else o['client_id'];notify(other,'تم تقديم طلب إلغاء',reason[:220],'cancellation',oid);notify_admins('طلب إلغاء يحتاج مراجعة',f"{o.get('title') or ('طلب #'+str(oid))}: {reason[:160]}",'cancellation',oid)
                    return self.sendj(201,cr)
            m=re.fullmatch(r'/api/v1/orders/(\d+)/timeline',p)
            if m and method=='GET':
                u=self.require();
                if not u:return
                oid=int(m.group(1));o=q('select id from orders where id=%s and (client_id=%s or freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                return self.sendj(200,{'items':order_timeline(oid)})
            m=re.fullmatch(r'/api/v1/orders/(\d+)/revisions',p)
            if m and method=='GET':
                u=self.require();
                if not u:return
                oid=int(m.group(1));o=q('select id from orders where id=%s and (client_id=%s or freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                return self.sendj(200,{'items':q('select rr.*,us.name requested_by_name from order_revision_requests rr join users us on us.id=rr.requested_by where rr.order_id=%s order by rr.sequence_no',(oid,))})
            m=re.fullmatch(r'/api/v1/orders/(\d+)/(attachments|deliveries)',p)
            if m and method=='GET':
                u=self.require();
                if not u:return
                oid=int(m.group(1));kind=m.group(2);o=q('select * from orders where id=%s and (client_id=%s or freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                if kind=='attachments':return self.sendj(200,{'items':public_attachments(q('select a.*,us.name uploaded_by_name from attachments a join users us on us.id=a.uploaded_by where a.order_id=%s order by a.created_at',(oid,)))})
                ds=q('select * from deliveries where order_id=%s order by created_at desc',(oid,))
                for d in ds:d['attachments']=public_attachments(q('select id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode,created_at from attachments where delivery_id=%s order by created_at',(d['id'],)))
                return self.sendj(200,{'items':ds})
            m=re.fullmatch(r'/api/v1/orders/(\d+)/messages',p)
            if m:
                u=self.require();
                if not u:return
                oid=int(m.group(1)); o=q('select id from orders where id=%s and (client_id=%s or freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                if not o:return self.sendj(404,{'error':'order_not_found'})
                if method=='GET':
                    msgs=q('select m.*,us.name sender_name,us.role sender_role from messages m join users us on us.id=m.sender_id where m.order_id=%s order by m.created_at',(oid,))
                    for msg in msgs: msg['attachments']=public_attachments(q('select id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode,created_at from attachments where message_id=%s order by created_at',(msg['id'],)))
                    return self.sendj(200,{'items':msgs})
                if method=='POST':
                    if q("select count(*)::int n from messages where sender_id=%s and created_at>now()-interval '1 hour'",(u['id'],),'one')['n']>=180:return self.sendj(429,{'error':'message_rate_limited','retry_after_seconds':3600})
                    b=self.body(); txt=str(b.get('body') or '').strip(); atts=clean_attachments(b.get('attachments'),uploaded_by=u['id'])
                    if not txt and not atts:return self.sendj(400,{'error':'message_required'})
                    if len(txt)>4000:return self.sendj(400,{'error':'message_too_long','maximum':4000})
                    msg=q('insert into messages(order_id,sender_id,body) values(%s,%s,%s) returning *',(oid,u['id'],txt or 'مرفق'),'one')
                    insert_attachments(u['id'],atts,order_id=oid,message_id=msg['id']); msg['attachments']=public_attachments(q('select id,file_name,file_url,storage_key,mime_type,size_bytes,storage_mode,created_at from attachments where message_id=%s order by created_at',(msg['id'],))); rec=q('select client_id,freelancer_id from orders where id=%s',(oid,),'one');other=rec['freelancer_id'] if int(u['id'])==int(rec['client_id']) else rec['client_id'];notify(other,'رسالة جديدة',txt[:220] or 'مرفق جديد','message',oid); return self.sendj(201,msg)
            if p=='/api/v1/notifications' and method=='GET':
                u=self.require();
                if not u:return
                where=['user_id=%s'];params=[u['id']];kind=(query.get('kind') or [''])[0].strip();unread_only=(query.get('unread') or [''])[0] in ('1','true','yes')
                if kind:where.append('kind=%s');params.append(kind)
                if unread_only:where.append('read_at is null')
                try:limit=max(1,min(int((query.get('limit') or ['100'])[0]),200))
                except Exception:limit=100
                items=q('select id,order_id,task_id,kind,title,body,read_at,created_at from user_notifications_v2 where '+' and '.join(where)+' order by created_at desc limit '+str(limit),tuple(params));
                unread=q('select count(*)::int n from user_notifications_v2 where user_id=%s and read_at is null',(u['id'],),'one')['n'];counts={x['kind']:x['n'] for x in q('select kind,count(*)::int n from user_notifications_v2 where user_id=%s group by kind',(u['id'],))};return self.sendj(200,{'items':items,'unread':unread,'counts':counts})
            if p=='/api/v1/notifications/read-all' and method=='POST':
                u=self.require();
                if not u:return
                q('update user_notifications_v2 set read_at=coalesce(read_at,now()) where user_id=%s',(u['id'],),None);return self.sendj(200,{'ok':True})
            m=re.fullmatch(r'/api/v1/notifications/(\d+)/read',p)
            if m and method=='POST':
                u=self.require();
                if not u:return
                q('update user_notifications_v2 set read_at=coalesce(read_at,now()) where id=%s and user_id=%s',(int(m.group(1)),u['id']),None);return self.sendj(200,{'ok':True})
            if p=='/api/v1/blocks' and method=='GET':
                u=self.require();
                if not u:return
                return self.sendj(200,{'items':q("select ub.blocked_id user_id,us.name,us.role,ub.reason,ub.created_at from user_blocks ub join users us on us.id=ub.blocked_id where ub.blocker_id=%s order by ub.created_at desc",(u['id'],))})
            m=re.fullmatch(r'/api/v1/blocks/(\d+)',p)
            if m and method in ('POST','DELETE'):
                u=self.require();
                if not u:return
                target=int(m.group(1))
                if target==int(u['id']):return self.sendj(400,{'error':'cannot_block_self'})
                tu=q('select id,name,role from users where id=%s',(target,),'one')
                if not tu:return self.sendj(404,{'error':'user_not_found'})
                if tu.get('role')=='admin':return self.sendj(403,{'error':'target_not_blockable'})
                if method=='DELETE':
                    q('delete from user_blocks where blocker_id=%s and blocked_id=%s',(u['id'],target),None);return self.sendj(200,{'ok':True,'user_id':target})
                b=self.body();reason=str(b.get('reason') or '').strip()[:500] or None
                q('insert into user_blocks(blocker_id,blocked_id,reason) values(%s,%s,%s) on conflict(blocker_id,blocked_id) do update set reason=excluded.reason,created_at=now()',(u['id'],target,reason),None)
                return self.sendj(201,{'ok':True,'user_id':target,'name':tu['name']})
            if p=='/api/v1/safety/reports':
                u=self.require();
                if not u:return
                if method=='GET':
                    return self.sendj(200,{'items':q("select sr.*,ru.name reported_user_name,t.title task_title from safety_reports sr left join users ru on ru.id=sr.reported_user_id left join tasks t on t.id=sr.task_id where sr.reporter_id=%s order by sr.created_at desc limit 100",(u['id'],))})
                if method=='POST':
                    b=self.body();cat=str(b.get('category') or 'other')
                    if cat not in ('spam','fraud','harassment','unsafe','prohibited_service','impersonation','other'):return self.sendj(400,{'error':'invalid_category'})
                    details=str(b.get('details') or '').strip()[:3000]
                    if len(details)<8:return self.sendj(400,{'error':'details_required'})
                    recent=q("select count(*)::int n from safety_reports where reporter_id=%s and created_at>now()-interval '1 hour'",(u['id'],),'one')['n']
                    if recent>=10:return self.sendj(429,{'error':'report_rate_limited','retry_after_seconds':3600})
                    uid=int(b.get('target_user_id') or 0) or None;tid=int(b.get('task_id') or 0) or None;oid=int(b.get('order_id') or 0) or None
                    if tid:
                        t=q('select id,client_id,title from tasks where id=%s',(tid,),'one')
                        if not t:return self.sendj(404,{'error':'task_not_found'})
                        uid=uid or t['client_id']
                    if oid:
                        o=q('select id,client_id,freelancer_id from orders where id=%s and (client_id=%s or freelancer_id=%s)',(oid,u['id'],u['id']),'one')
                        if not o:return self.sendj(404,{'error':'order_not_found'})
                        uid=uid or (o['freelancer_id'] if int(o['client_id'])==int(u['id']) else o['client_id'])
                    if uid:
                        tu=q('select id,role from users where id=%s',(uid,),'one')
                        if not tu:return self.sendj(404,{'error':'user_not_found'})
                        if int(uid)==int(u['id']):return self.sendj(400,{'error':'cannot_report_self'})
                    if not any((uid,tid,oid)):return self.sendj(400,{'error':'report_target_required'})
                    dup=q("select id from safety_reports where reporter_id=%s and coalesce(reported_user_id,0)=coalesce(%s,0) and coalesce(task_id,0)=coalesce(%s,0) and coalesce(order_id,0)=coalesce(%s,0) and status in ('open','in_review') limit 1",(u['id'],uid,tid,oid),'one')
                    if dup:return self.sendj(409,{'error':'active_report_exists','report_id':dup['id']})
                    r=q("insert into safety_reports(reporter_id,reported_user_id,task_id,order_id,category,details) values(%s,%s,%s,%s,%s,%s) returning *",(u['id'],uid,tid,oid,cat,details),'one')
                    notify_admins('بلاغ أمان جديد',details[:220],'safety_report',oid,tid)
                    return self.sendj(201,r)
            if p=='/api/v1/team' and method=='GET':
                u=self.require('client');
                if not u:return
                return self.sendj(200,{'items':q('select f.freelancer_id,us.name,fp.bio,fp.skills,fp.rating,fp.completed_tasks,fp.on_time_rate,fp.avg_response_minutes,fp.is_available,fp.kyc_status,f.note from favorite_freelancers f join users us on us.id=f.freelancer_id left join freelancer_profiles fp on fp.user_id=f.freelancer_id where f.client_id=%s order by f.created_at desc',(u['id'],))})
            m=re.fullmatch(r'/api/v1/team/(\d+)',p)
            if m:
                u=self.require('client');
                if not u:return
                fid=int(m.group(1))
                if method=='POST':
                    worked=q('select 1 x from orders where client_id=%s and freelancer_id=%s limit 1',(u['id'],fid),'one')
                    if not worked:return self.sendj(403,{'error':'no_shared_order'})
                    b=self.body();q('insert into favorite_freelancers(client_id,freelancer_id,note) values(%s,%s,%s) on conflict(client_id,freelancer_id) do update set note=excluded.note',(u['id'],fid,str(b.get('note') or '')[:300] or None),None);return self.sendj(201,{'ok':True})
                if method=='DELETE':q('delete from favorite_freelancers where client_id=%s and freelancer_id=%s',(u['id'],fid),None);return self.sendj(200,{'ok':True})
            if p=='/api/v1/support/tickets':
                u=self.require();
                if not u:return
                if method=='GET':return self.sendj(200,{'items':q('select * from support_tickets where user_id=%s order by updated_at desc',(u['id'],))})
                if method=='POST':
                    if q("select count(*)::int n from support_tickets where user_id=%s and created_at>now()-interval '1 day'",(u['id'],),'one')['n']>=10:return self.sendj(429,{'error':'support_rate_limited','retry_after_seconds':86400})
                    b=self.body();sub=str(b.get('subject') or '').strip();msg=str(b.get('message') or '').strip()
                    if not sub or not msg:return self.sendj(400,{'error':'missing_fields'})
                    return self.sendj(201,q("insert into support_tickets(user_id,category,subject,message,priority,status) values(%s,%s,%s,%s,%s,'open') returning *",(u['id'],b.get('category') or 'general',sub[:180],msg[:5000],b.get('priority') or 'normal'),'one'))
            if p=='/api/v1/privacy/requests':
                u=self.require();
                if not u:return
                if method=='GET':return self.sendj(200,{'items':q('select * from privacy_requests where user_id=%s order by created_at desc',(u['id'],))})
                if method=='POST':
                    b=self.body();typ=str(b.get('request_type') or '')
                    if typ not in ('access','export','correct','delete','restrict'):return self.sendj(400,{'error':'invalid_type'})
                    if q("select id from privacy_requests where user_id=%s and request_type=%s and status in ('pending','in_progress')",(u['id'],typ),'one'):return self.sendj(409,{'error':'active_request_exists'})
                    if q("select count(*)::int n from privacy_requests where user_id=%s and created_at>now()-interval '1 day'",(u['id'],),'one')['n']>=5:return self.sendj(429,{'error':'privacy_rate_limited','retry_after_seconds':86400})
                    return self.sendj(201,q('insert into privacy_requests(user_id,request_type,details) values(%s,%s,%s) returning *',(u['id'],typ,str(b.get('details') or '')[:2500] or None),'one'))
            if p.startswith('/api/admin'):
                u=self.require('admin');
                if not u:return
                if p=='/api/admin/summary' and method=='GET':
                    return self.sendj(200,{'users':q('select count(*)::int n from users',(), 'one')['n'],'tasks':q('select count(*)::int n from tasks',(), 'one')['n'],'orders':q('select count(*)::int n from orders',(), 'one')['n'],'open_support':q("select count(*)::int n from support_tickets where status='open'",(), 'one')['n'],'pending_privacy':q("select count(*)::int n from privacy_requests where status='pending'",(), 'one')['n'],'open_disputes':q("select count(*)::int n from order_disputes where status in ('open','in_review')",(), 'one')['n']})
                if p=='/api/admin/operations' and method=='GET':
                    metrics={'new_users_24h':q("select count(*)::int n from users where created_at>now()-interval '24 hours'",(), 'one')['n'],'open_tasks':q("select count(*)::int n from tasks where status='open'",(), 'one')['n'],'awaiting_payment':q("select count(*)::int n from orders where status='awaiting_payment'",(), 'one')['n'],'active_orders':q("select count(*)::int n from orders where status in ('in_progress','revision_requested')",(), 'one')['n'],'delivered_waiting':q("select count(*)::int n from orders where status='delivered'",(), 'one')['n'],'open_disputes':q("select count(*)::int n from order_disputes where status in ('open','in_review')",(), 'one')['n'],'pending_cancellations':q("select count(*)::int n from order_cancellation_requests where status in ('pending','in_review')",(), 'one')['n'],'pending_payouts':q("select count(*)::int n from payout_requests where status in ('pending','processing')",(), 'one')['n'],'open_safety_reports':q("select count(*)::int n from safety_reports where status in ('open','in_review')",(), 'one')['n'],'open_support':q("select count(*)::int n from support_tickets where status in ('open','in_progress')",(), 'one')['n'],'pending_privacy':q("select count(*)::int n from privacy_requests where status in ('pending','in_progress')",(), 'one')['n']}
                    funnel={'tasks_7d':q("select count(*)::int n from tasks where created_at>now()-interval '7 days'",(), 'one')['n'],'proposals_7d':q("select count(*)::int n from proposals where created_at>now()-interval '7 days'",(), 'one')['n'],'orders_7d':q("select count(*)::int n from orders where created_at>now()-interval '7 days'",(), 'one')['n'],'completed_7d':q("select count(*)::int n from orders where completed_at>now()-interval '7 days'",(), 'one')['n']}
                    obs=operational_snapshot()
                    return self.sendj(200,{'metrics':metrics,'funnel':funnel,'audit':q("select aal.*,u.name admin_name from admin_audit_logs aal join users u on u.id=aal.admin_id order by aal.created_at desc limit 40"),'operational':obs})
                if p=='/api/admin/disputes' and method=='GET':
                    return self.sendj(200,{'items':q("select d.*,t.title,cu.name client_name,fu.name freelancer_name,ou.name opened_by_name from order_disputes d join orders o on o.id=d.order_id join tasks t on t.id=o.task_id join users cu on cu.id=o.client_id join users fu on fu.id=o.freelancer_id join users ou on ou.id=d.opened_by order by case when d.status in ('open','in_review') then 0 else 1 end,d.created_at desc limit 300")})
                m=re.fullmatch(r'/api/admin/disputes/(\d+)',p)
                if m and method=='PATCH':
                    b=self.body();did=int(m.group(1));d=q('select d.*,o.task_id,o.client_id,o.freelancer_id,o.payment_status from order_disputes d join orders o on o.id=d.order_id where d.id=%s',(did,),'one')
                    if not d:return self.sendj(404,{'error':'dispute_not_found'})
                    if d.get('status')=='resolved':return self.sendj(409,{'error':'dispute_finalized'})
                    if d.get('status') not in ('open','in_review'):return self.sendj(409,{'error':'invalid_dispute_state','state':d.get('status')})
                    st=str(b.get('status') or '')
                    if st=='in_review':
                        return self.sendj(200,q("update order_disputes set status='in_review',resolution_note=%s,updated_at=now() where id=%s returning *",(str(b.get('resolution_note') or '')[:3000] or None,did),'one'))
                    if st=='resolved':
                        action=str(b.get('action') or '')
                        if action not in ('resume','cancel'):return self.sendj(400,{'error':'invalid_resolution_action'})
                        refund='not_needed'
                        if action=='resume':
                            prev_order_status=d.get('previous_order_status') or 'in_progress';ts=d.get('previous_task_status') or ('delivered' if prev_order_status=='delivered' else 'in_progress')
                            if prev_order_status in ('disputed','completed','cancelled'):prev_order_status='in_progress'
                            if ts in ('disputed','completed','cancelled'):ts='in_progress'
                            q('update orders set status=%s where id=%s',(prev_order_status,d['order_id']),None);q('update tasks set status=%s,updated_at=now() where id=%s',(ts,d['task_id']),None)
                        else:
                            if d.get('payment_status')=='paid':
                                if PAYMENT_MODE=='mock':
                                    q("update orders set status='cancelled',payment_status='refunded' where id=%s",(d['order_id'],),None);refund='refunded'
                                else:
                                    q("update orders set status='cancelled' where id=%s",(d['order_id'],),None);refund='manual_required'
                            else:
                                q("update orders set status='cancelled' where id=%s",(d['order_id'],),None)
                            q("update tasks set status='cancelled',updated_at=now() where id=%s",(d['task_id'],),None)
                            if refund=='manual_required':
                                operational_event('warning','payment','dispute_cancel_refund_required','Cancelled dispute has a paid order that requires provider refund',self.request_id(),u['id'],'order',d['order_id'],{'dispute_id':did})
                                notify_admins('استرداد مطلوب بعد إلغاء نزاع',f"الطلب #{d['order_id']} مدفوع وتم إلغاؤه بقرار نزاع؛ يلزم تنفيذ الاسترداد لدى مزود الدفع",'payment',d['order_id'])
                        res=q("update order_disputes set status='resolved',resolution_action=%s,resolution_note=%s,resolved_by=%s,resolved_at=now(),updated_at=now() where id=%s returning *",(action,str(b.get('resolution_note') or '')[:3000] or None,u['id'],did),'one')
                        ttl='تم استئناف الطلب بعد النزاع' if action=='resume' else 'تم إلغاء الطلب بعد النزاع'
                        msg=str(b.get('resolution_note') or '')[:180]
                        if refund=='manual_required':msg=(msg+' · جارٍ معالجة استرداد المبلغ').strip(' ·')
                        notify(d['client_id'],ttl,msg or None,'dispute',d['order_id']);notify(d['freelancer_id'],ttl,msg or None,'dispute',d['order_id'])
                        return self.sendj(200,{**res,'refund_status':refund,'refund_action_required':refund=='manual_required'})
                    return self.sendj(400,{'error':'invalid_status'})
                if p=='/api/admin/cancellations' and method=='GET':
                    return self.sendj(200,{'items':q("select cr.*,t.title,o.payment_status,o.amount,cu.name client_name,fu.name freelancer_name,ru.name requested_by_name from order_cancellation_requests cr join orders o on o.id=cr.order_id join tasks t on t.id=o.task_id join users cu on cu.id=o.client_id join users fu on fu.id=o.freelancer_id join users ru on ru.id=cr.requested_by order by case when cr.status in ('pending','in_review') then 0 else 1 end,cr.created_at desc limit 300")})
                m=re.fullmatch(r'/api/admin/cancellations/(\d+)',p)
                if m and method=='PATCH':
                    cid=int(m.group(1));b=self.body();cr=q('select cr.*,o.task_id,o.client_id,o.freelancer_id,o.payment_status from order_cancellation_requests cr join orders o on o.id=cr.order_id where cr.id=%s',(cid,),'one')
                    if not cr:return self.sendj(404,{'error':'cancellation_not_found'})
                    if b.get('refund_status')=='refunded':
                        if cr.get('status')!='approved' or cr.get('refund_status') not in ('manual_required','pending'):return self.sendj(409,{'error':'refund_not_markable'})
                        q("update orders set payment_status='refunded' where id=%s",(cr['order_id'],),None)
                        r=q("update order_cancellation_requests set refund_status='refunded',admin_note=coalesce(%s,admin_note),updated_at=now() where id=%s returning *",(str(b.get('admin_note') or '')[:3000] or None,cid),'one')
                        notify(cr['client_id'],'تم تحديث حالة الاسترداد','تم تسجيل المبلغ كمسترد بعد المعالجة لدى مزود الدفع','cancellation',cr['order_id']);return self.sendj(200,r)
                    st=str(b.get('status') or '')
                    note=str(b.get('admin_note') or '')[:3000] or None
                    if st=='in_review':
                        if cr.get('status') not in ('pending','in_review'):return self.sendj(409,{'error':'cancellation_finalized'})
                        return self.sendj(200,q("update order_cancellation_requests set status='in_review',admin_note=%s,updated_at=now() where id=%s returning *",(note,cid),'one'))
                    if st=='rejected':
                        if cr.get('status') not in ('pending','in_review'):return self.sendj(409,{'error':'cancellation_finalized'})
                        r=q("update order_cancellation_requests set status='rejected',admin_note=%s,resolved_by=%s,resolved_at=now(),updated_at=now() where id=%s returning *",(note,u['id'],cid),'one');notify(cr['client_id'],'تم رفض طلب الإلغاء',note or 'يمكن متابعة الطلب','cancellation',cr['order_id']);notify(cr['freelancer_id'],'تم رفض طلب الإلغاء',note or 'يمكن متابعة الطلب','cancellation',cr['order_id']);return self.sendj(200,r)
                    if st=='approved':
                        if cr.get('status') not in ('pending','in_review'):return self.sendj(409,{'error':'cancellation_finalized'})
                        refund='not_needed'
                        if cr.get('payment_status')=='paid':
                            if PAYMENT_MODE=='mock':q("update orders set status='cancelled',payment_status='refunded' where id=%s",(cr['order_id'],),None);refund='refunded'
                            else:q("update orders set status='cancelled' where id=%s",(cr['order_id'],),None);refund='manual_required'
                        else:q("update orders set status='cancelled' where id=%s",(cr['order_id'],),None)
                        q("update tasks set status='cancelled',updated_at=now() where id=%s",(cr['task_id'],),None)
                        r=q("update order_cancellation_requests set status='approved',refund_status=%s,admin_note=%s,resolved_by=%s,resolved_at=now(),updated_at=now() where id=%s returning *",(refund,note,u['id'],cid),'one')
                        msg=(note or 'تم اعتماد الإلغاء')+(' · يلزم معالجة الاسترداد لدى مزود الدفع' if refund=='manual_required' else '')
                        notify(cr['client_id'],'تم اعتماد إلغاء الطلب',msg[:220],'cancellation',cr['order_id']);notify(cr['freelancer_id'],'تم اعتماد إلغاء الطلب',msg[:220],'cancellation',cr['order_id']);return self.sendj(200,{**r,'refund_action_required':refund=='manual_required'})
                    return self.sendj(400,{'error':'invalid_status'})
                if p=='/api/admin/safety/reports' and method=='GET':
                    st=(query.get('status') or [''])[0]
                    params=[];where=''
                    if st in ('open','in_review','resolved','dismissed'):where=' where sr.status=%s';params=[st]
                    items=q("""select sr.*,rp.name reporter_name,ru.name reported_user_name,ru.role reported_user_role,t.title task_title,
                        coalesce(tm.hidden,false) task_hidden,coalesce(um.interaction_restricted,false) user_restricted
                        from safety_reports sr join users rp on rp.id=sr.reporter_id
                        left join users ru on ru.id=sr.reported_user_id left join tasks t on t.id=sr.task_id
                        left join task_moderation tm on tm.task_id=sr.task_id left join user_moderation um on um.user_id=sr.reported_user_id
                        """+where+" order by case when sr.status in ('open','in_review') then 0 else 1 end,sr.created_at desc limit 300",tuple(params))
                    return self.sendj(200,{'items':items})
                if p=='/api/admin/safety/actions' and method=='GET':
                    return self.sendj(200,{'items':q("select ma.*,au.name admin_name,tu.name target_user_name,t.title task_title from moderation_actions ma join users au on au.id=ma.admin_id left join users tu on tu.id=ma.target_user_id left join tasks t on t.id=ma.task_id order by ma.created_at desc limit 150")})
                m=re.fullmatch(r'/api/admin/safety/reports/(\d+)',p)
                if m and method=='PATCH':
                    rid=int(m.group(1));b=self.body();sr=q('select * from safety_reports where id=%s',(rid,),'one')
                    if not sr:return self.sendj(404,{'error':'report_not_found'})
                    note=str(b.get('admin_note') or '')[:3000] or None
                    st=str(b.get('status') or sr.get('status') or 'open')
                    if st not in ('open','in_review','resolved','dismissed'):return self.sendj(400,{'error':'invalid_status'})
                    ta=str(b.get('task_action') or '')
                    if ta in ('hide','restore') and sr.get('task_id'):
                        hidden=ta=='hide';q("insert into task_moderation(task_id,hidden,reason,updated_by) values(%s,%s,%s,%s) on conflict(task_id) do update set hidden=excluded.hidden,reason=excluded.reason,updated_by=excluded.updated_by,updated_at=now()",(sr['task_id'],hidden,note,u['id']),None)
                        q('insert into moderation_actions(report_id,admin_id,task_id,action,note) values(%s,%s,%s,%s,%s)',(rid,u['id'],sr['task_id'],'hide_task' if hidden else 'restore_task',note),None)
                    ua=str(b.get('user_action') or '')
                    if ua in ('restrict','unrestrict') and sr.get('reported_user_id'):
                        target=q('select id,role from users where id=%s',(sr['reported_user_id'],),'one')
                        if target and target.get('role')=='admin':return self.sendj(403,{'error':'admin_not_restrictable'})
                        restricted=ua=='restrict';q("insert into user_moderation(user_id,interaction_restricted,reason,updated_by) values(%s,%s,%s,%s) on conflict(user_id) do update set interaction_restricted=excluded.interaction_restricted,reason=excluded.reason,updated_by=excluded.updated_by,updated_at=now()",(sr['reported_user_id'],restricted,note,u['id']),None)
                        q('insert into moderation_actions(report_id,admin_id,target_user_id,action,note) values(%s,%s,%s,%s,%s)',(rid,u['id'],sr['reported_user_id'],'restrict_user' if restricted else 'unrestrict_user',note),None)
                        notify(sr['reported_user_id'],'تحديث من فريق الأمان','تم تقييد التعاملات الجديدة على الحساب مؤقتًا' if restricted else 'تم رفع تقييد التعاملات الجديدة عن الحساب','safety',None,sr.get('task_id'))
                    resolved=st in ('resolved','dismissed')
                    r=q("update safety_reports set status=%s,admin_note=%s,resolved_by=case when %s then %s else resolved_by end,resolved_at=case when %s then now() else null end,updated_at=now() where id=%s returning *",(st,note,resolved,u['id'],resolved,rid),'one')
                    q('insert into moderation_actions(report_id,admin_id,target_user_id,task_id,action,note) values(%s,%s,%s,%s,%s,%s)',(rid,u['id'],sr.get('reported_user_id'),sr.get('task_id'),'report_'+st,note),None)
                    if resolved:notify(sr['reporter_id'],'تم تحديث بلاغ الأمان','تمت مراجعة البلاغ وإغلاقه' if st=='resolved' else 'تمت مراجعة البلاغ ولم يتطلب إجراء إضافيًا','safety',sr.get('order_id'),sr.get('task_id'))
                    admin_audit(u['id'],'safety_report_updated','safety_report',rid,{'status':st,'task_action':ta,'user_action':ua})
                    return self.sendj(200,r)
                if p=='/api/admin/orders' and method=='GET':
                    return self.sendj(200,{'items':q("""select o.id,o.task_id,o.client_id,o.freelancer_id,o.amount,o.platform_fee,o.status,o.payment_status,o.created_at,
                        t.title,t.due_at,t.urgency,c.name client_name,f.name freelancer_name,
                        coalesce(p.delivery_hours,0) promised_hours,coalesce(p.revisions,0) revisions_allowed,
                        (select count(*)::int from order_revision_requests rr where rr.order_id=o.id) revisions_used,
                        greatest(coalesce(p.revisions,0)-(select count(*)::int from order_revision_requests rr where rr.order_id=o.id),0) revisions_remaining
                        from orders o join tasks t on t.id=o.task_id join users c on c.id=o.client_id join users f on f.id=o.freelancer_id
                        left join proposals p on p.id=o.proposal_id
                        order by case when o.status in ('awaiting_payment','in_progress','revision_requested','delivered','disputed') then 0 else 1 end,o.created_at desc limit 300""")})
                if p=='/api/admin/users' and method=='GET':return self.sendj(200,{'items':q('select us.id,us.phone,us.name,us.role,us.is_verified,us.created_at,fp.rating,fp.completed_tasks,fp.is_available,fp.kyc_status,(select array_agg(ur.role order by ur.role) from user_roles ur where ur.user_id=us.id and ur.enabled=true) roles from users us left join freelancer_profiles fp on fp.user_id=us.id order by us.created_at desc limit 300')})
                m=re.fullmatch(r'/api/admin/freelancers/(\d+)/kyc',p)
                if m and method=='PATCH':
                    if KYC_MODE!='manual':return self.sendj(409,{'error':'kyc_managed_by_provider'})
                    b=self.body();st=str(b.get('status') or '')
                    if st not in ('pending','approved','rejected'):return self.sendj(400,{'error':'invalid_status'})
                    r=q('update freelancer_profiles set kyc_status=%s where user_id=%s returning *',(st,int(m.group(1))),'one')
                    if not r:return self.sendj(404,{'error':'freelancer_not_found'})
                    admin_audit(u['id'],'kyc_status_updated','user',m.group(1),{'status':st});return self.sendj(200,r)
                if p=='/api/admin/payouts' and method=='GET':
                    items=q("""select pr.*,us.name freelancer_name,us.phone,fp.kyc_status
                               from payout_requests pr join users us on us.id=pr.freelancer_id
                               left join freelancer_profiles fp on fp.user_id=pr.freelancer_id
                               order by case when pr.status in ('pending','processing') then 0 else 1 end,pr.created_at desc limit 300""")
                    for x in items:x['balance']=freelancer_earnings(x['freelancer_id'])
                    return self.sendj(200,{'items':items})
                m=re.fullmatch(r'/api/admin/payouts/(\d+)',p)
                if m and method=='PATCH':
                    b=self.body();pid=int(m.group(1));st=str(b.get('status') or '')
                    if st not in ('processing','paid','rejected','cancelled'):return self.sendj(400,{'error':'invalid_status'})
                    pr=q('select * from payout_requests where id=%s',(pid,),'one')
                    if not pr:return self.sendj(404,{'error':'payout_not_found'})
                    if pr.get('status') in ('paid','rejected','cancelled'):return self.sendj(409,{'error':'payout_finalized'})
                    if st=='paid' and pr.get('status') not in ('pending','processing'):return self.sendj(409,{'error':'invalid_payout_state'})
                    r=q("""update payout_requests set status=%s,admin_note=%s,updated_at=now(),resolved_at=case when %s in ('paid','rejected','cancelled') then now() else resolved_at end where id=%s returning *""",(st,str(b.get('admin_note') or '')[:1000] or None,st,pid),'one')
                    ttl={'processing':'طلب السحب قيد المعالجة','paid':'تم تنفيذ السحب','rejected':'تم رفض طلب السحب','cancelled':'تم إلغاء طلب السحب'}[st]
                    notify(pr['freelancer_id'],ttl,str(b.get('admin_note') or '')[:220] or None,'payout',None)
                    admin_audit(u['id'],'payout_status_updated','payout',pid,{'status':st})
                    return self.sendj(200,{'item':r,'balance':freelancer_earnings(pr['freelancer_id'])})
                if p=='/api/admin/support' and method=='GET':return self.sendj(200,{'items':q('select s.*,us.name,us.phone from support_tickets s join users us on us.id=s.user_id order by s.created_at desc limit 300')})
                m=re.fullmatch(r'/api/admin/support/(\d+)',p)
                if m and method=='PATCH':
                    b=self.body();st=str(b.get('status') or 'in_progress')
                    if st not in ('in_progress','resolved','closed'):return self.sendj(400,{'error':'invalid_status'})
                    r=q('update support_tickets set status=%s,admin_reply=%s,updated_at=now() where id=%s returning *',(st,str(b.get('admin_reply') or '')[:3000] or None,int(m.group(1))),'one')
                    if not r:return self.sendj(404,{'error':'support_ticket_not_found'})
                    admin_audit(u['id'],'support_updated','support_ticket',m.group(1),{'status':st});return self.sendj(200,r)
                if p=='/api/admin/privacy' and method=='GET':return self.sendj(200,{'items':q('select pr.*,us.name,us.phone from privacy_requests pr join users us on us.id=pr.user_id order by pr.created_at desc limit 300')})
                m=re.fullmatch(r'/api/admin/privacy/(\d+)',p)
                if m and method=='PATCH':
                    b=self.body();st=str(b.get('status') or 'in_progress')
                    if st not in ('in_progress','completed','rejected'):return self.sendj(400,{'error':'invalid_status'})
                    pid=int(m.group(1));pr=q('select id,status from privacy_requests where id=%s',(pid,),'one')
                    if not pr:return self.sendj(404,{'error':'privacy_request_not_found'})
                    if pr.get('status') in ('completed','rejected') and st!=pr.get('status'):return self.sendj(409,{'error':'privacy_request_finalized'})
                    r=q("update privacy_requests set status=%s,admin_note=%s,resolved_at=case when %s in ('completed','rejected') then coalesce(resolved_at,now()) else null end where id=%s returning *",(st,str(b.get('admin_note') or '')[:3000] or None,st,pid),'one')
                    admin_audit(u['id'],'privacy_request_updated','privacy_request',pid,{'status':st});return self.sendj(200,r)
            return self.sendj(404,{'error':'not_found'})
        except ValueError as e:
            code=str(e)
            if code in ('invalid_json','too_large'):
                return self.sendj(400,{'error':code})
            print('BAD_REQUEST',self.request_id(),repr(e),flush=True)
            return self.sendj(400,{'error':'invalid_request'})
        except Exception as e:
            operational_event('error','http','internal_error',repr(e),self.request_id(),None,'route',getattr(self,'path',''))
            print('ERR',self.request_id(),repr(e),flush=True)
            return self.sendj(500,{'error':'internal_error'})

if __name__=='__main__':
    # Migrations are the canonical schema source. Runtime ensure is kept only
    # as an explicit emergency/dev compatibility switch and is OFF by default.
    if RUN_RUNTIME_SCHEMA_ENSURE:
        ensure_schema()
        ensure_services_schema()
        ensure_roles_schema()
        ensure_timeline_schema()
        ensure_notifications_schema()
        ensure_engagement_schema()
        ensure_payout_schema()
    ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
