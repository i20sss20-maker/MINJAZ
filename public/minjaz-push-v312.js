(function(){
  const ID='minjazPushCardV312';
  const once=new Map();
  function tr(ar,en){return (document.documentElement.lang||'ar').toLowerCase().startsWith('en')?en:ar}
  function supported(){return 'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window}
  function b64ToBytes(value){
    const pad='='.repeat((4-value.length%4)%4);
    const raw=atob((value+pad).replace(/-/g,'+').replace(/_/g,'/'));
    return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)));
  }
  async function config(){
    if(!window.me?.user||typeof api!=='function')return {enabled:false};
    const x=await api('/api/v1/push/config');
    return x?.r?.ok&&x?.j?x.j:{enabled:false};
  }
  async function currentSub(){
    if(!supported())return null;
    try{const reg=await navigator.serviceWorker.ready;return await reg.pushManager.getSubscription()}catch(_){return null}
  }
  async function registerSub(sub){
    if(!sub||typeof api!=='function')return false;
    const x=await api('/api/v1/push/subscriptions',{method:'POST',body:JSON.stringify({subscription:sub.toJSON()})});
    return !!x?.r?.ok;
  }
  function toastSafe(msg){try{if(typeof toast==='function')toast(msg)}catch(_){}}
  window.enableMinjazPushV312=async function(){
    if(!supported()){toastSafe(tr('الإشعارات غير مدعومة على هذا الجهاز.','Notifications are not supported on this device.'));return}
    try{
      const cfg=await config();
      if(!cfg.enabled||!cfg.public_key){toastSafe(tr('خدمة الإشعارات غير متاحة حاليًا.','Notification service is currently unavailable.'));return}
      const permission=await Notification.requestPermission();
      if(permission!=='granted'){await syncCard();return}
      const reg=await navigator.serviceWorker.ready;
      let sub=await reg.pushManager.getSubscription();
      if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(cfg.public_key)});
      if(await registerSub(sub))toastSafe(tr('تم تفعيل الإشعارات.','Notifications enabled.'));
      await syncCard();
    }catch(err){
      report('push_enable_error',String(err?.message||err),'warning');
      toastSafe(tr('تعذر تفعيل الإشعارات الآن.','Could not enable notifications right now.'));
      await syncCard();
    }
  };
  window.disableMinjazPushV312=async function(){
    try{
      const sub=await currentSub();
      if(sub&&typeof api==='function')await api('/api/v1/push/subscriptions',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint})});
      if(sub)await sub.unsubscribe().catch(()=>{});
      toastSafe(tr('تم إيقاف إشعارات هذا الجهاز.','Notifications disabled on this device.'));
    }catch(err){report('push_disable_error',String(err?.message||err),'warning')}
    await syncCard();
  };
  async function syncExisting(){
    if(!window.me?.user||!supported()||Notification.permission!=='granted')return;
    const sub=await currentSub();
    if(sub)await registerSub(sub).catch(()=>false);
  }
  async function syncCard(){
    const host=document.getElementById('account');
    if(!host||!window.me?.user)return;
    let card=document.getElementById(ID);
    if(!card){card=document.createElement('section');card.id=ID;card.className='card';host.appendChild(card)}
    if(!supported()){
      card.innerHTML='<h3>'+tr('إشعارات مِنجاز','MINJAZ notifications')+'</h3><p class="muted">'+tr('هذا الجهاز لا يدعم إشعارات الويب. داخل التطبيق تظل التنبيهات موجودة في مركز الإشعارات.','This device does not support Web Push. In-app notifications remain available.')+'</p>';
      return;
    }
    const cfg=await config();
    if(!cfg.enabled){
      card.innerHTML='<h3>'+tr('إشعارات مِنجاز','MINJAZ notifications')+'</h3><p class="muted">'+tr('الخدمة قيد التجهيز. تنبيهاتك داخل مِنجاز تعمل بشكل طبيعي.','Push delivery is being prepared. Your in-app notifications still work normally.')+'</p>';
      return;
    }
    const sub=await currentSub(),granted=Notification.permission==='granted'&&!!sub;
    card.innerHTML='<div class="row space"><div><h3 style="margin:0">'+tr('إشعارات مِنجاز','MINJAZ notifications')+'</h3><p class="muted" style="margin:6px 0 0">'+(granted?tr('مفعلة على هذا الجهاز — بننبهك بالرسائل والتسليمات والتحديثات المهمة.','Enabled on this device for messages, deliveries, and important updates.'):tr('فعّلها عشان توصلك التحديثات المهمة حتى لو مِنجاز مو مفتوح.','Enable notifications for important updates while MINJAZ is closed.'))+'</p></div><button class="btn '+(granted?'ghost':'primary')+'" onclick="'+(granted?'disableMinjazPushV312()':'enableMinjazPushV312()')+'">'+(granted?tr('إيقاف','Disable'):tr('تفعيل','Enable'))+'</button></div>';
  }
  async function report(code,message,level='warning',meta={}){
    if(!window.me?.user||typeof api!=='function')return;
    const key=code+':'+String(message||'').slice(0,80),now=Date.now();
    if(now-(once.get(key)||0)<60000)return;
    once.set(key,now);
    try{await api('/api/v1/telemetry/client',{method:'POST',body:JSON.stringify({area:'web',code,message:String(message||'').slice(0,500),level,meta})})}catch(_){}
  }
  window.reportMinjazClientV312=report;
  const baseRender=window.renderAccount;
  if(typeof baseRender==='function')window.renderAccount=async function(){
    const out=await baseRender.apply(this,arguments);
    try{await syncCard();await syncExisting()}catch(_){}
    return out;
  };
  window.addEventListener('error',event=>{
    const src=String(event.filename||'').split('/').pop();
    report('js_error',event.message||'JavaScript error','error',{source:src,line:event.lineno||0,column:event.colno||0});
  });
  window.addEventListener('unhandledrejection',event=>{
    report('unhandled_rejection',String(event.reason?.message||event.reason||'Unhandled promise rejection'),'error');
  });
  window.addEventListener('load',()=>setTimeout(()=>{syncExisting().catch(()=>{})},1200));
})();
