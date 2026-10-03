(function(){
  function lang(){return (window.minjazLangV15&&window.minjazLangV15())||document.documentElement.lang||'ar'}
  function t(ar,en){return lang()==='en'?en:ar}
  function e(v){if(typeof esc==='function')return esc(v==null?'':String(v));return String(v==null?'':v).replace(/[&<>"']/g,function(c){return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]})}
  function m(v){return typeof money==='function'?money(v):Number(v||0).toLocaleString(lang()==='en'?'en-US':'ar-SA')+' SAR'}
  function when(v){try{return v?new Date(v).toLocaleString(lang()==='en'?'en-US':'ar-SA'):''}catch(_){return''}}
  function freshLabel(){if(!state.updatedAt)return t('غير محدّث','Not updated');var sec=Math.max(0,Math.round((Date.now()-state.updatedAt)/1000));if(sec<10)return t('محدّث الآن','Updated now');if(sec<60)return t('محدّث قبل '+sec+' ث','Updated '+sec+'s ago');var min=Math.floor(sec/60);return t('محدّث قبل '+min+' د','Updated '+min+'m ago')}
  var state={data:null,loading:false,updatedAt:0};

  function ensurePage(){
    if(document.getElementById('workcenter'))return;
    var x=document.createElement('section');x.id='workcenter';x.className='page';
    var files=document.getElementById('files');if(files)files.insertAdjacentElement('afterend',x);else document.querySelector('.content')?.appendChild(x);
  }

  function ensureNav(){
    if(!window.me?.user||me.user.role==='admin')return;
    try{
      ['client','freelancer'].forEach(function(role){
        var a=navByRole&&navByRole[role];if(!Array.isArray(a))return;
        var item=a.find(function(x){return x[0]==='workcenter'});
        if(item)item[2]=t('مركز العمل','Work center');
        else a.splice(1,0,['workcenter','🧭',t('مركز العمل','Work center')]);
      });
      if(typeof buildNav==='function')buildNav();
    }catch(_){}
  }

  async function get(path){
    try{var x=await api(path);return x?.r?.ok?x.j:null}catch(_){return null}
  }

  function buildActions(data){
    var role=me?.user?.role,orders=data.orders||[],tasks=data.tasks||[],proposals=data.proposals||[],out=[];
    function add(priority,kind,title,desc,label,action,meta){out.push({priority:priority,kind:kind,title:title,desc:desc,label:label,action:action,meta:meta||''})}
    if(role==='client'){
      tasks.filter(function(x){return x.status==='open'&&Number(x.proposal_count||0)>0}).forEach(function(x){
        add(1,'proposal',t('وصلتك عروض','Offers received'),x.title,t('راجع العروض','Review offers'),'taskOffers('+Number(x.id)+')',Number(x.proposal_count||0)+' '+t('عرض','offers'));
      });
      orders.filter(function(x){return x.status==='awaiting_payment'&&x.payment_status==='unpaid'}).forEach(function(x){
        add(1,'payment',t('طلب ينتظر الدفع','Payment required'),x.title,t('إكمال الدفع','Complete payment'),'orderModal('+Number(x.id)+')',m(x.amount));
      });
      orders.filter(function(x){return x.status==='delivered'}).forEach(function(x){
        add(1,'delivery',t('تسليم ينتظر مراجعتك','Delivery awaiting review'),x.title,t('مراجعة التسليم','Review delivery'),'orderModal('+Number(x.id)+')','');
      });
      orders.filter(function(x){return x.status==='completed'&&!x.reviewed}).forEach(function(x){
        add(2,'review',t('أضف تقييمك','Add your review'),x.title,t('فتح الطلب','Open order'),'orderModal('+Number(x.id)+')','');
      });
      if(!out.length&&tasks.filter(function(x){return x.status==='open'}).length===0)add(5,'start',t('ابدأ مهمة جديدة','Start a new task'),t('أنشئ طلبك الأول وابدأ استقبال العروض.','Create a task and start receiving offers.'),t('إنشاء مهمة','Create task'),'newTaskModal()','');
    }else if(role==='freelancer'){
      orders.filter(function(x){return x.status==='revision_requested'}).forEach(function(x){
        add(1,'revision',t('طلب تعديل','Revision requested'),x.title,t('راجع الملاحظات','Review notes'),'orderModal('+Number(x.id)+')','');
      });
      orders.filter(function(x){return x.status==='in_progress'}).forEach(function(x){
        add(2,'active',t('عمل قيد التنفيذ','Work in progress'),x.title,t('متابعة الطلب','Open order'),'orderModal('+Number(x.id)+')',x.promised_hours?x.promised_hours+'h':'');
      });
      var sent=proposals.filter(function(x){return (x.proposal_status||x.status)==='sent'}).length;
      if(sent)add(3,'proposal',t('عروض بانتظار الرد','Proposals awaiting reply'),t('عندك '+sent+' عرض ما زال مفتوحًا.',sent+' proposals are still open.'),t('عرض الفرص','View opportunities'),"go('tasks')",sent+'');
      if(!out.length)add(5,'browse',t('اكتشف فرص جديدة','Find new opportunities'),t('حدّث مهاراتك وتصفح المهام المناسبة لك.','Browse tasks that fit your skills.'),t('تصفح المهام','Browse tasks'),"go('tasks')",'');
    }
    return out.sort(function(a,b){return a.priority-b.priority}).slice(0,6);
  }

  function actionCard(x){
    return '<div class="wcActionV31"><div><b>'+e(x.title)+'</b><p>'+e(x.desc||'')+'</p><div class="wcMetaV31">'+(x.meta?'<span class="pill gray">'+e(x.meta)+'</span>':'')+'<span class="pill blue">'+e(x.kind)+'</span></div></div><button class="btn '+(x.priority===1?'primary':'ghost')+'" onclick="'+x.action+'">'+e(x.label)+'</button></div>';
  }

  function conversationCard(x){
    var unread=Number(x.unread_messages||0);
    return '<div class="wcConversationV31"><div><b>'+e(x.title||x.counterpart_name||t('محادثة','Conversation'))+'</b><p>'+e(x.last_message||t('مرفق جديد','New attachment'))+'</p><div class="wcMetaV31"><span class="pill gray">'+e(x.counterpart_name||'')+'</span>'+(unread?'<span class="pill amber">'+unread+' '+t('غير مقروء','unread')+'</span>':'')+(x.last_message_at?'<span class="pill gray">'+e(when(x.last_message_at))+'</span>':'')+'</div></div><button class="btn ghost" onclick="orderModal('+Number(x.order_id)+')">'+t('فتح','Open')+'</button></div>';
  }

  function fileCard(x){
    var link=x.file_url?'<a class="btn ghost" target="_blank" rel="noopener" href="'+e(x.file_url)+'">'+t('فتح','Open')+'</a>':(x.order_id?'<button class="btn ghost" onclick="orderModal('+Number(x.order_id)+')">'+t('الطلب','Order')+'</button>':'');
    return '<div class="wcFileV31"><div><b>📎 '+e(x.file_name||t('ملف','File'))+'</b><p>'+e(x.task_title||'')+'</p><div class="wcMetaV31"><span class="pill gray">'+e(x.source_type||'file')+'</span>'+(x.uploaded_by_name?'<span class="pill gray">'+e(x.uploaded_by_name)+'</span>':'')+'</div></div>'+link+'</div>';
  }

  function notifCard(x){
    return '<div class="wcNotifV31"><b>'+e(x.title||t('تنبيه','Notification'))+'</b><p>'+e(x.body||'')+'</p><div class="wcMetaV31"><span class="pill '+(x.read_at?'gray':'amber')+'">'+(x.read_at?t('مقروء','Read'):t('جديد','New'))+'</span>'+(x.created_at?'<span class="pill gray">'+e(when(x.created_at))+'</span>':'')+'</div></div>';
  }

  function paint(data,partial){
    ensurePage();var host=document.getElementById('workcenter');if(!host)return;
    var orders=data.orders||[],conversations=data.conversations||[],files=data.files||[],notifications=data.notifications||[],actions=buildActions(data);
    var active=orders.filter(function(x){return !['completed','cancelled'].includes(x.status)}).length;
    var unread=conversations.reduce(function(s,x){return s+Number(x.unread_messages||0)},0);
    var role=me?.user?.role;
    host.innerHTML='<div class="workCenterV31">'+
      '<section class="wcHeroV31"><div class="wcHeroTopV31"><div><div class="wcVersionV311"><span class="pill blue">v31.1</span><span class="pill gray wcFreshV311">'+e(freshLabel())+'</span></div><h2>'+t('مركز العمل','Work center')+'</h2><p>'+t('طلباتك ورسائلك وملفاتك والخطوات اللي تحتاج منك إجراء — كلها في مكان واحد.','Orders, messages, files, and next actions in one place.')+'</p></div><button class="btn ghost wcRefreshV31" onclick="renderWorkCenterV31(true)">↻ '+t('تحديث','Refresh')+'</button></div><div class="wcQuickV31">'+
      (role==='client'?'<button class="btn primary" onclick="newTaskModal()">＋ '+t('مهمة جديدة','New task')+'</button>':'<button class="btn primary" onclick="go(\'tasks\')">'+t('استكشف الفرص','Browse opportunities')+'</button>')+
      '<button class="btn ghost" onclick="go(\'orders\')">'+t('الطلبات','Orders')+'</button><button class="btn ghost" onclick="go(\'inbox\')">'+t('الرسائل','Messages')+'</button><button class="btn ghost" onclick="go(\'files\')">'+t('الملفات','Files')+'</button></div></section>'+
      '<div class="wcMetricsV31"><div class="wcMetricV31"><b>'+actions.length+'</b><small>'+t('إجراءات مقترحة','Suggested actions')+'</small></div><div class="wcMetricV31"><b>'+active+'</b><small>'+t('طلبات نشطة','Active orders')+'</small></div><div class="wcMetricV31"><b>'+unread+'</b><small>'+t('رسائل غير مقروءة','Unread messages')+'</small></div><div class="wcMetricV31"><b>'+files.length+'</b><small>'+t('ملفات مرتبطة','Linked files')+'</small></div></div>'+
      (partial?'<div class="pill amber">'+t('بعض البيانات تعذر تحديثها — المعروض هو المتاح الآن.','Some data could not refresh; showing available data.')+'</div>':'')+
      '<div class="wcGridV31"><section class="wcPanelV31"><div class="wcPanelHeadV31"><div><h3>'+t('وش يحتاج منك الآن','What needs you now')+'</h3><small>'+t('مرتبة حسب الأولوية','Prioritized for you')+'</small></div><span class="pill '+(actions.length?'amber':'green')+'">'+actions.length+'</span></div><div class="wcListV31">'+(actions.map(actionCard).join('')||'<div class="wcEmptyV31">'+t('ما عندك إجراء عاجل حاليًا.','No urgent action right now.')+'</div>')+'</div></section>'+
      '<section class="wcPanelV31"><div class="wcPanelHeadV31"><div><h3>'+t('آخر المحادثات','Recent conversations')+'</h3><small>'+t('أحدث تواصل في أعمالك','Latest work messages')+'</small></div><button class="btn ghost" onclick="go(\'inbox\')">'+t('الكل','All')+'</button></div><div class="wcListV31">'+(conversations.slice(0,4).map(conversationCard).join('')||'<div class="wcEmptyV31">'+t('ما عندك محادثات بعد.','No conversations yet.')+'</div>')+'</div></section>'+
      '<section class="wcPanelV31"><div class="wcPanelHeadV31"><div><h3>'+t('آخر الملفات','Recent files')+'</h3><small>'+t('مرفقات الطلبات والمحادثات','Order and chat attachments')+'</small></div><button class="btn ghost" onclick="go(\'files\')">'+t('الكل','All')+'</button></div><div class="wcListV31">'+(files.slice(0,5).map(fileCard).join('')||'<div class="wcEmptyV31">'+t('ما فيه ملفات مرتبطة حتى الآن.','No linked files yet.')+'</div>')+'</div></section>'+
      '<section class="wcPanelV31"><div class="wcPanelHeadV31"><div><h3>'+t('آخر التنبيهات','Recent notifications')+'</h3><small>'+t('الأحدث أولًا','Newest first')+'</small></div><button class="btn ghost" onclick="go(\'notifications\')">'+t('الكل','All')+'</button></div><div class="wcListV31">'+(notifications.slice(0,5).map(notifCard).join('')||'<div class="wcEmptyV31">'+t('ما عندك تنبيهات جديدة.','No new notifications.')+'</div>')+'</div></section></div>'+
      '</div>';
  }

  window.renderWorkCenterV31=async function(force){
    ensurePage();var host=document.getElementById('workcenter');if(!host||state.loading)return;
    if(state.data&&!force)paint(state.data,false);
    else host.innerHTML='<div class="card empty">'+t('جاري تجهيز مركز العمل…','Loading work center…')+'</div>';
    state.loading=true;
    var role=me?.user?.role;
    var req=[
      get('/api/v1/orders'),
      get(role==='client'?'/api/v1/tasks?limit=200':'/api/v1/tasks?sort=match&limit=20'),
      get('/api/v1/conversations'),
      get('/api/v1/files'),
      get('/api/v1/notifications?limit=30'),
      role==='freelancer'?get('/api/v1/freelancer/proposals'):Promise.resolve({items:[]})
    ];
    var r=await Promise.all(req);state.loading=false;
    var data={
      orders:r[0]?.items||[],
      tasks:r[1]?.items||[],
      conversations:r[2]?.items||[],
      files:r[3]?.items||[],
      notifications:r[4]?.items||[],
      proposals:r[5]?.items||[]
    };
    var partial=r.some(function(x){return x===null});
    state.data=data;state.updatedAt=Date.now();paint(data,partial);
  };

  var baseGoV31=window.go;
  if(typeof baseGoV31==='function')window.go=async function(id){
    ensurePage();ensureNav();
    var out=await baseGoV31.apply(this,arguments);
    if(id==='workcenter'){
      var title=document.getElementById('pageTitle'),sub=document.getElementById('pageSub');
      if(title)title.textContent=t('مركز العمل','Work center');
      if(sub)sub.textContent=t('كل أعمالك وإجراءاتك في شاشة واحدة','Your work and next actions in one place');
      await window.renderWorkCenterV31(false);
    }
    return out;
  };

  var baseBootV31=window.boot;
  if(typeof baseBootV31==='function')window.boot=async function(){
    var out=await baseBootV31.apply(this,arguments);ensurePage();ensureNav();return out;
  };

  document.addEventListener('visibilitychange',function(){
    if(document.visibilityState!=='visible')return;
    var page=document.getElementById('workcenter');
    if(page?.classList.contains('on')&&Date.now()-Number(state.updatedAt||0)>30000)window.renderWorkCenterV31(true);
  });
  window.addEventListener('focus',function(){
    var page=document.getElementById('workcenter');
    if(page?.classList.contains('on')&&Date.now()-Number(state.updatedAt||0)>30000)window.renderWorkCenterV31(true);
  });

  setTimeout(function(){ensurePage();if(window.me?.user)ensureNav()},250);
})();
