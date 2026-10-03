(function(){
  function e(v){return typeof esc==='function'?esc(v):String(v??'')}
  function info(ok,reachable){return ok?{text:'جاهز',cls:'green'}:reachable?{text:'ناقص إعداد',cls:'amber'}:{text:'غير متاح',cls:'red'}}
  function card(title,sub,ready,reachable,detail){
    const s=info(ready,reachable);
    return '<div class="opsCard500" style="min-height:82px"><div class="row space" style="align-items:flex-start"><b style="font-size:12px">'+e(title)+'</b><span class="pill '+s.cls+'">'+s.text+'</span></div><small style="display:block;margin-top:7px">'+e(sub)+'</small>'+(detail?'<small style="display:block;margin-top:4px;color:#94a3b8">'+e(detail)+'</small>':'')+'</div>';
  }
  function draw(host,p){
    if(!host||host.querySelector('[data-provider-v315]'))return;
    p=p||{};
    const push=p.push||{},pay=p.payments||{},intg=p.integrations||{},sms=intg.sms||{},kyc=intg.kyc||{};
    const sec=document.createElement('div');sec.dataset.providerV315='1';
    sec.innerHTML='<div class="sectionHead"><div><h2>جاهزية الخدمات الخارجية</h2><p>فحص حي من السيرفر بدون عرض أي مفاتيح أو أسرار.</p></div><span class="pill blue">v31.5</span></div><div class="opsGrid500">'+
      card('Push Notifications','تنبيهات الويب',!!push.provider_configured,!!push.reachable,push.latency_ms!=null?push.latency_ms+'ms':'')+
      card('Moyasar','الدفع المستضاف',!!pay.provider_configured,!!pay.reachable,pay.provider_mode&&pay.provider_mode!=='unknown'?'وضع '+pay.provider_mode:'')+
      card('SMS','رموز الدخول · '+(sms.provider||'unknown'),!!sms.configured,!!intg.reachable,'')+
      card('KYC','توثيق المستقل · '+(kyc.provider||'unknown'),!!kyc.configured,!!intg.reachable,'')+
      '</div>';
    const ops=host.querySelector('[data-ops-v500]');
    if(ops)ops.appendChild(sec);else host.prepend(sec);
  }
  const base=window.renderAdmin;
  if(typeof base==='function')window.renderAdmin=async function(){
    await base.apply(this,arguments);
    if(!window.me?.user||window.me.user.role!=='admin')return;
    const host=document.getElementById('admin');if(!host||host.querySelector('[data-provider-v315]'))return;
    try{const x=await api('/api/admin/operations');if(x&&x.r&&x.r.ok)draw(host,x.j&&x.j.providers||{})}catch(_){}
  };
})();
