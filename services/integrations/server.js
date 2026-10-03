'use strict';

const http=require('http');
const crypto=require('crypto');

const PORT=Number(process.env.PORT||3000);
const ADAPTER_SECRET=String(process.env.INTEGRATIONS_ADAPTER_BEARER||process.env.AUTH_SECRET||'');
const SMS_PROVIDER=String(process.env.SMS_PROVIDER||'unifonic').trim().toLowerCase();
const UNIFONIC_APPSID=String(process.env.UNIFONIC_APPSID||'').trim();
const UNIFONIC_SENDER_ID=String(process.env.UNIFONIC_SENDER_ID||'').trim();

const KYC_PROVIDER=String(process.env.KYC_PROVIDER||'disabled').trim().toLowerCase();
const KYC_PROVIDER_START_URL=String(process.env.KYC_PROVIDER_START_URL||'').trim();
const KYC_PROVIDER_API_KEY=String(process.env.KYC_PROVIDER_API_KEY||'').trim();
const KYC_PROVIDER_AUTH_HEADER=String(process.env.KYC_PROVIDER_AUTH_HEADER||'Authorization').trim()||'Authorization';
const KYC_PROVIDER_AUTH_PREFIX=String(process.env.KYC_PROVIDER_AUTH_PREFIX||'Bearer').trim();
const KYC_PROVIDER_REFERENCE_FIELD=String(process.env.KYC_PROVIDER_REFERENCE_FIELD||'reference').trim();
const KYC_PROVIDER_URL_FIELD=String(process.env.KYC_PROVIDER_URL_FIELD||'verification_url').trim();

function safeEqual(a,b){
  const aa=Buffer.from(String(a||'')),bb=Buffer.from(String(b||''));
  return aa.length===bb.length&&aa.length>0&&crypto.timingSafeEqual(aa,bb);
}
function authorized(req){
  const h=String(req.headers.authorization||'');
  return ADAPTER_SECRET.length>=16&&h.startsWith('Bearer ')&&safeEqual(h.slice(7).trim(),ADAPTER_SECRET);
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
async function readJson(req,max=131072){
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
function normalizeSaudiPhone(value){
  const digits=String(value||'').replace(/\D/g,'');
  if(/^9665\d{8}$/.test(digits))return digits;
  if(/^05\d{8}$/.test(digits))return '966'+digits.slice(1);
  if(/^5\d{8}$/.test(digits))return '966'+digits;
  return '';
}
function smsConfigured(){
  return SMS_PROVIDER==='unifonic'&&UNIFONIC_APPSID.length>=12&&UNIFONIC_SENDER_ID.length>=2;
}
function kycConfigured(){
  if(KYC_PROVIDER==='disabled'||KYC_PROVIDER==='none'||!KYC_PROVIDER)return false;
  try{
    const u=new URL(KYC_PROVIDER_START_URL);
    return u.protocol==='https:'&&KYC_PROVIDER_API_KEY.length>=12;
  }catch(_){return false}
}
async function sendUnifonicSms(payload){
  if(!smsConfigured())throw Object.assign(new Error('sms_provider_not_configured'),{status:503});
  const recipient=normalizeSaudiPhone(payload.phone);
  const code=String(payload.code||'').trim();
  const challengeId=String(payload.challenge_id||'').slice(0,120);
  if(!recipient||!/^\d{4,8}$/.test(code))throw Object.assign(new Error('invalid_sms_payload'),{status:400});

  const body='رمز التحقق في مِنجاز: '+code+'\nلا تشارك الرمز مع أي شخص.';
  const form=new URLSearchParams({
    AppSid:UNIFONIC_APPSID,
    SenderID:UNIFONIC_SENDER_ID,
    Recipient:recipient,
    Body:body,
    responseType:'JSON',
    CorrelationID:challengeId||crypto.randomUUID(),
    baseEncode:'true',
    async:'false'
  });
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),8000);
  try{
    const response=await fetch('https://el.cloud.unifonic.com/rest/SMS/messages',{
      method:'POST',
      headers:{'accept':'application/json','content-type':'application/x-www-form-urlencoded'},
      body:form.toString(),
      signal:ctl.signal
    });
    const text=await response.text();
    let data={};
    try{data=text?JSON.parse(text):{}}catch(_){data={raw:text.slice(0,500)}}
    if(!response.ok||data.success===false||String(data.errorCode||'')==='ER-04'){
      console.error('UNIFONIC_SEND_FAILED',response.status,String(data.errorCode||''),String(data.message||'').slice(0,180));
      throw Object.assign(new Error('sms_provider_rejected'),{status:502});
    }
    return {
      ok:true,
      provider:'unifonic',
      provider_message_id:String(data?.data?.MessageID||'').slice(0,180)||null,
      status:String(data?.data?.Status||'queued').slice(0,80)
    };
  }finally{clearTimeout(timer)}
}
async function startGenericKyc(payload){
  if(!kycConfigured())throw Object.assign(new Error('kyc_provider_not_configured'),{status:503});
  const uid=Number(payload.user_id||0);
  if(!Number.isInteger(uid)||uid<=0)throw Object.assign(new Error('invalid_user_id'),{status:400});
  const reqBody={
    user_id:uid,
    phone:String(payload.phone||'').slice(0,40),
    name:String(payload.name||'').slice(0,160),
    return_url:String(payload.return_url||'').slice(0,1000)||null,
    webhook_url:String(payload.webhook_url||'').slice(0,1000)||null,
    webhook_contract:'minjaz-kyc-v1'
  };
  const headers={'accept':'application/json','content-type':'application/json'};
  headers[KYC_PROVIDER_AUTH_HEADER]=(KYC_PROVIDER_AUTH_PREFIX?KYC_PROVIDER_AUTH_PREFIX+' ':'')+KYC_PROVIDER_API_KEY;
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),10000);
  try{
    const response=await fetch(KYC_PROVIDER_START_URL,{method:'POST',headers,body:JSON.stringify(reqBody),signal:ctl.signal});
    const text=await response.text();
    let data={};
    try{data=text?JSON.parse(text):{}}catch(_){data={}}
    if(!response.ok)throw Object.assign(new Error('kyc_provider_http_'+response.status),{status:502});
    const verificationUrl=String(data[KYC_PROVIDER_URL_FIELD]||data.verification_url||data.url||'').trim();
    const reference=String(data[KYC_PROVIDER_REFERENCE_FIELD]||data.provider_reference||data.reference||data.id||'').trim();
    let parsed=null;try{parsed=new URL(verificationUrl)}catch(_){}
    if(!parsed||parsed.protocol!=='https:'||!reference)throw Object.assign(new Error('invalid_kyc_provider_response'),{status:502});
    return {verification_url:verificationUrl,provider_reference:reference.slice(0,180)};
  }finally{clearTimeout(timer)}
}

const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://localhost');
    if(req.method==='GET'&&url.pathname==='/health'){
      return json(res,200,{
        ok:true,
        sms:{provider:SMS_PROVIDER,configured:smsConfigured()},
        kyc:{provider:KYC_PROVIDER,configured:kycConfigured()}
      });
    }
    if(!authorized(req))return json(res,401,{error:'unauthorized'});
    if(req.method==='POST'&&url.pathname==='/v1/sms/send'){
      const payload=await readJson(req);
      if(SMS_PROVIDER!=='unifonic')return json(res,503,{error:'unsupported_sms_provider'});
      return json(res,200,await sendUnifonicSms(payload));
    }
    if(req.method==='POST'&&url.pathname==='/v1/kyc/start'){
      return json(res,200,await startGenericKyc(await readJson(req)));
    }
    return json(res,404,{error:'not_found'});
  }catch(err){
    const status=Number(err&&err.status||0)||500;
    console.error('INTEGRATIONS_ERR',String(err&&err.message||err));
    return json(res,status,{error:status>=500?'integration_unavailable':String(err.message||'invalid_request')});
  }
});

server.listen(PORT,'0.0.0.0',()=>{
  console.log('MINJAZ_INTEGRATIONS_READY','sms_configured='+smsConfigured(),'sms_provider='+SMS_PROVIDER,'kyc_configured='+kycConfigured(),'kyc_provider='+KYC_PROVIDER);
});
