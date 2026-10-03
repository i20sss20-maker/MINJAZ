'use strict';

const http=require('http');
const crypto=require('crypto');
const {Pool}=require('pg');

const PORT=Number(process.env.PORT||3000);
const ADAPTER_SECRET=String(process.env.PAYMENT_ADAPTER_BEARER||process.env.AUTH_SECRET||'');
const MOYASAR_SECRET_KEY=String(process.env.MOYASAR_SECRET_KEY||'');
const MOYASAR_WEBHOOK_SECRET=String(process.env.MOYASAR_WEBHOOK_SECRET||process.env.AUTH_SECRET||'');
const AUTO_REGISTER_WEBHOOK=String(process.env.AUTO_REGISTER_WEBHOOK||'0')==='1';
const PUBLIC_BASE=(String(process.env.PAYMENTS_PUBLIC_BASE_URL||'').replace(/\/$/,'') ||
  (process.env.RAILWAY_PUBLIC_DOMAIN?'https://'+process.env.RAILWAY_PUBLIC_DOMAIN:''));

const pool=new Pool({
  host:process.env.PGHOST,
  port:Number(process.env.PGPORT||5432),
  user:process.env.PGUSER,
  password:process.env.PGPASSWORD,
  database:process.env.PGDATABASE,
  max:8,
  idleTimeoutMillis:30000
});

function configured(){
  return ADAPTER_SECRET.length>=24 &&
    /^sk_(test|live)_/.test(MOYASAR_SECRET_KEY) &&
    MOYASAR_WEBHOOK_SECRET.length>=24;
}
function secureEqual(a,b){
  const aa=Buffer.from(String(a||'')),bb=Buffer.from(String(b||''));
  return aa.length===bb.length&&aa.length>0&&crypto.timingSafeEqual(aa,bb);
}
function authorized(req){
  const h=String(req.headers.authorization||'');
  return h.startsWith('Bearer ')&&secureEqual(h.slice(7).trim(),ADAPTER_SECRET);
}
function json(res,status,obj){
  const out=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{
    'content-type':'application/json; charset=utf-8',
    'content-length':out.length,
    'cache-control':'no-store',
    'x-content-type-options':'nosniff'
  });
  res.end(out);
}
async function readJson(req,max=262144){
  const chunks=[];let size=0;
  for await(const chunk of req){
    size+=chunk.length;
    if(size>max)throw Object.assign(new Error('payload_too_large'),{status:413});
    chunks.push(chunk);
  }
  if(!chunks.length)return {};
  try{return JSON.parse(Buffer.concat(chunks).toString('utf8'))}
  catch(_){throw Object.assign(new Error('invalid_json'),{status:400})}
}
function httpsUrl(value){
  try{return new URL(String(value||'')).protocol==='https:'}catch(_){return false}
}
function centsFromSar(value){
  const n=Number(value);
  if(!Number.isFinite(n)||n<=0)throw Object.assign(new Error('invalid_amount'),{status:400});
  const halalas=Math.round(n*100);
  if(halalas<100)throw Object.assign(new Error('amount_below_provider_minimum'),{status:400});
  return halalas;
}
function hmacHex(secret,raw){
  return crypto.createHmac('sha256',secret).update(raw).digest('hex');
}
function basicAuth(){
  return 'Basic '+Buffer.from(MOYASAR_SECRET_KEY+':').toString('base64');
}
async function moyasar(path,method='GET',payload=null){
  if(!/^sk_(test|live)_/.test(MOYASAR_SECRET_KEY))throw Object.assign(new Error('moyasar_not_configured'),{status:503});
  const ctl=new AbortController();
  const timer=setTimeout(()=>ctl.abort(),8000);
  try{
    const response=await fetch('https://api.moyasar.com/v1'+path,{
      method,
      headers:{
        'accept':'application/json',
        'authorization':basicAuth(),
        ...(payload?{'content-type':'application/json'}:{})
      },
      body:payload?JSON.stringify(payload):undefined,
      signal:ctl.signal
    });
    const text=await response.text();
    let body={};
    try{body=text?JSON.parse(text):{}}catch(_){body={raw:text.slice(0,1000)}}
    if(!response.ok){
      const err=Object.assign(new Error('moyasar_http_'+response.status),{status:502,provider_status:response.status,provider_body:body});
      throw err;
    }
    return body;
  }finally{clearTimeout(timer)}
}
async function ensureSchema(){
  await pool.query(`create table if not exists moyasar_invoice_links(
    invoice_id text primary key,
    order_id bigint not null,
    amount_halalas bigint not null,
    webhook_url text not null,
    checkout_url text,
    provider_status text not null default 'initiated',
    last_event_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(order_id)
  )`);
  await pool.query('create index if not exists idx_moyasar_invoice_links_order on moyasar_invoice_links(order_id)');
}
async function linkForInvoice(invoiceId){
  return (await pool.query('select * from moyasar_invoice_links where invoice_id=$1',[String(invoiceId)])).rows[0]||null;
}
async function sendNormalized(link,eventId,eventType,amountHalalas){
  if(!link||!httpsUrl(link.webhook_url))throw new Error('missing_minjaz_webhook');
  const payload={
    event_id:String(eventId).slice(0,180),
    type:eventType,
    order_id:Number(link.order_id),
    provider_payment_id:String(link.invoice_id).slice(0,180),
    amount:Number(amountHalalas)/100
  };
  const raw=JSON.stringify(payload);
  const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),5000);
  try{
    const response=await fetch(link.webhook_url,{
      method:'POST',
      headers:{
        'content-type':'application/json',
        'x-minjaz-signature':hmacHex(MOYASAR_WEBHOOK_SECRET,raw)
      },
      body:raw,
      signal:ctl.signal
    });
    if(!response.ok)throw new Error('minjaz_webhook_http_'+response.status);
    await pool.query('update moyasar_invoice_links set provider_status=$2,last_event_id=$3,updated_at=now() where invoice_id=$1',
      [link.invoice_id,eventType==='payment.succeeded'?'paid':'failed',String(eventId).slice(0,180)]);
  }finally{clearTimeout(timer)}
}
async function createCheckout(payload){
  const orderId=Number(payload.order_id||0);
  if(!Number.isInteger(orderId)||orderId<=0)throw Object.assign(new Error('invalid_order_id'),{status:400});
  if(String(payload.currency||'SAR').toUpperCase()!=='SAR')throw Object.assign(new Error('unsupported_currency'),{status:400});
  if(!httpsUrl(payload.return_url)||!httpsUrl(payload.webhook_url))throw Object.assign(new Error('invalid_return_or_webhook_url'),{status:400});
  const amount=centsFromSar(payload.amount);

  const existing=(await pool.query('select * from moyasar_invoice_links where order_id=$1',[orderId])).rows[0];
  if(existing&&existing.checkout_url){
    return {checkout_url:existing.checkout_url,provider_payment_id:existing.invoice_id,reused:true};
  }

  const callbackSeed=orderId+'|'+payload.webhook_url;
  const callbackSig=hmacHex(ADAPTER_SECRET,callbackSeed);
  const callbackUrl=PUBLIC_BASE?
    PUBLIC_BASE+'/v1/moyasar/invoice-callback?order_id='+encodeURIComponent(orderId)+'&sig='+callbackSig:
    undefined;

  const invoice=await moyasar('/invoices','POST',{
    amount,
    currency:'SAR',
    description:'MINJAZ Order #'+orderId,
    success_url:payload.return_url,
    back_url:payload.return_url,
    ...(callbackUrl?{callback_url:callbackUrl}:{}),
    metadata:{minjaz_order_id:String(orderId),minjaz_contract:'v1'}
  });
  if(!invoice.id||!httpsUrl(invoice.url))throw Object.assign(new Error('invalid_moyasar_invoice'),{status:502});

  await pool.query(`insert into moyasar_invoice_links(invoice_id,order_id,amount_halalas,webhook_url,checkout_url,provider_status)
    values($1,$2,$3,$4,$5,$6)
    on conflict(order_id) do update set invoice_id=excluded.invoice_id,amount_halalas=excluded.amount_halalas,
      webhook_url=excluded.webhook_url,checkout_url=excluded.checkout_url,provider_status=excluded.provider_status,updated_at=now()`,
    [String(invoice.id),orderId,amount,String(payload.webhook_url),String(invoice.url),String(invoice.status||'initiated')]);

  return {checkout_url:String(invoice.url),provider_payment_id:String(invoice.id),reused:false};
}
async function processGlobalWebhook(event){
  if(!secureEqual(event.secret_token,MOYASAR_WEBHOOK_SECRET))throw new Error('invalid_moyasar_secret_token');
  if(!['payment_paid','payment_failed'].includes(String(event.type||'')))return;
  const payment=event.data||{};
  const invoiceId=String(payment.invoice_id||'');
  if(!invoiceId)return;
  const link=await linkForInvoice(invoiceId);
  if(!link)return;
  if(Number(payment.amount||0)!==Number(link.amount_halalas))throw new Error('provider_amount_mismatch');
  const normalized=event.type==='payment_paid'?'payment.succeeded':'payment.failed';
  await sendNormalized(link,String(event.id||('moyasar:'+event.type+':'+invoiceId)),normalized,Number(payment.amount));
}
async function processInvoiceCallback(invoice,orderId,sig){
  const rawOrder=String(orderId||'');
  if(!/^\d+$/.test(rawOrder))throw new Error('invalid_order_id');
  const link=(await pool.query('select * from moyasar_invoice_links where order_id=$1',[Number(rawOrder)])).rows[0];
  if(!link)throw new Error('invoice_link_not_found');
  const expected=hmacHex(ADAPTER_SECRET,rawOrder+'|'+link.webhook_url);
  if(!secureEqual(sig,expected))throw new Error('invalid_callback_signature');
  const invoiceId=String(invoice.id||link.invoice_id||'');
  if(invoiceId!==String(link.invoice_id))throw new Error('invoice_mismatch');
  const verified=await moyasar('/invoices/'+encodeURIComponent(invoiceId),'GET');
  if(String(verified.id)!==invoiceId||Number(verified.amount)!==Number(link.amount_halalas))throw new Error('invoice_verification_failed');
  if(String(verified.status)!=='paid')return;
  const eventId='invoice-paid:'+invoiceId+':'+String(verified.updated_at||verified.created_at||'v1');
  await sendNormalized(link,eventId,'payment.succeeded',Number(verified.amount));
}
async function ensureProviderWebhook(){
  if(!AUTO_REGISTER_WEBHOOK||!configured()||!PUBLIC_BASE)return {enabled:false};
  const target=PUBLIC_BASE+'/v1/moyasar/webhook';
  const list=await moyasar('/webhooks','GET');
  const items=Array.isArray(list.webhooks)?list.webhooks:[];
  const existing=items.find(x=>String(x.url||'')===target);
  if(existing)return {enabled:true,existing:true,id:existing.id};
  const created=await moyasar('/webhooks','POST',{
    http_method:'post',
    url:target,
    shared_secret:MOYASAR_WEBHOOK_SECRET,
    events:['payment_paid','payment_failed']
  });
  return {enabled:true,existing:false,id:created.id||null};
}

const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://localhost');
    if(req.method==='GET'&&url.pathname==='/health'){
      let database=false;try{await pool.query('select 1');database=true}catch(_){}
      return json(res,200,{ok:database,database,moyasar_configured:configured(),webhook_auto_register:AUTO_REGISTER_WEBHOOK,provider_mode:MOYASAR_SECRET_KEY.startsWith('sk_live_')?'live':(MOYASAR_SECRET_KEY.startsWith('sk_test_')?'test':'missing')});
    }
    if(req.method==='POST'&&url.pathname==='/v1/moyasar/webhook'){
      const payload=await readJson(req);
      if(!secureEqual(payload.secret_token,MOYASAR_WEBHOOK_SECRET))return json(res,401,{error:'invalid_secret_token'});
      json(res,202,{ok:true,accepted:true});
      setImmediate(()=>processGlobalWebhook(payload).catch(err=>console.error('MOYASAR_WEBHOOK_ERR',err.message)));
      return;
    }
    if(req.method==='POST'&&url.pathname==='/v1/moyasar/invoice-callback'){
      const payload=await readJson(req);
      const orderId=url.searchParams.get('order_id')||'';
      const sig=url.searchParams.get('sig')||'';
      json(res,202,{ok:true,accepted:true});
      setImmediate(()=>processInvoiceCallback(payload,orderId,sig).catch(err=>console.error('MOYASAR_CALLBACK_ERR',err.message)));
      return;
    }
    if(!authorized(req))return json(res,401,{error:'unauthorized'});
    if(req.method==='POST'&&url.pathname==='/v1/payments/create'){
      if(!configured())return json(res,503,{error:'payment_adapter_not_configured'});
      const out=await createCheckout(await readJson(req));
      return json(res,201,out);
    }
    if(req.method==='POST'&&url.pathname==='/v1/provider-webhook/ensure'){
      if(!configured())return json(res,503,{error:'payment_adapter_not_configured'});
      const out=await ensureProviderWebhook();
      return json(res,200,out);
    }
    return json(res,404,{error:'not_found'});
  }catch(err){
    const status=Number(err&&err.status||0)||500;
    console.error('PAYMENTS_ERR',err&&err.message||err);
    return json(res,status,{error:status>=500?'payment_adapter_error':String(err.message||'invalid_request')});
  }
});

ensureSchema().then(async()=>{
  console.log('MINJAZ_PAYMENTS_READY','moyasar_configured='+configured(),'provider_mode='+(MOYASAR_SECRET_KEY.startsWith('sk_live_')?'live':(MOYASAR_SECRET_KEY.startsWith('sk_test_')?'test':'missing')));
  if(AUTO_REGISTER_WEBHOOK){
    try{console.log('MINJAZ_MOYASAR_WEBHOOK',JSON.stringify(await ensureProviderWebhook()))}
    catch(err){console.error('MOYASAR_WEBHOOK_SETUP_ERR',err.message)}
  }
  server.listen(PORT,'0.0.0.0');
}).catch(err=>{console.error('PAYMENTS_BOOT_ERR',err);process.exit(1)});
