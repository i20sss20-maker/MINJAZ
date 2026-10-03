(function(){
  let cfg=null;
  const params=new URLSearchParams(location.search);
  const deleteIntent=params.get('delete_account')==='1';

  async function publicConfig(){
    if(cfg)return cfg;
    try{
      const r=await fetch('/api/v1/public/config',{credentials:'same-origin'});
      cfg=r.ok?await r.json():{};
    }catch(_){cfg={}}
    return cfg;
  }

  function productionText(){
    if(!cfg||cfg.release_channel!=='production')return;
    document.documentElement.dataset.releaseChannel='production';
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    const replacements=[
      ['MINJAZ BETA','MINJAZ'],
      ['نسخة Beta — مسودات تحتاج مراجعة قانونية قبل الإطلاق التجاري','الشروط والسياسات الحالية'],
      ['باستخدام مِنجاز أنت تستخدم نسخة Beta.','باستخدام مِنجاز أنت توافق على الشروط والسياسات الحالية.']
    ];
    let n;
    while((n=walker.nextNode())){
      let v=n.nodeValue||'',next=v;
      for(const pair of replacements)next=next.split(pair[0]).join(pair[1]);
      if(next!==v)n.nodeValue=next;
    }
  }

  async function existingDeletion(){
    try{
      const x=await api('/api/v1/privacy/requests');
      if(!x?.r?.ok)return null;
      return (x.j?.items||[]).find(v=>v.request_type==='delete'&&['pending','in_progress'].includes(v.status))||null;
    }catch(_){return null}
  }

  window.openAccountDeletionV316=async function(){
    const active=await existingDeletion();
    if(active){
      openModal('<div class="modalHead"><h2>حذف الحساب</h2><button class="x" onclick="closeModal()">×</button></div><div class="card"><b>طلب الحذف قيد المعالجة</b><p style="font-size:9px;color:#64748b;line-height:1.8">طلبك موجود بالفعل وحالته: '+esc(active.status)+'. تقدر تتابعه من قسم الخصوصية والبيانات.</p></div>');
      return;
    }
    openModal('<div class="modalHead"><h2>طلب حذف الحساب</h2><button class="x" onclick="closeModal()">×</button></div><div class="orderAlert cancelled">حذف الحساب إجراء مهم. إذا عندك طلب نشط أو نزاع أو التزام مالي، قد يلزم تسويته أولًا. وقد نحتفظ فقط بالسجلات المطلوبة نظاميًا أو ماليًا أو أمنيًا.</div><label style="display:flex;gap:8px;align-items:flex-start;margin-top:12px"><input id="deleteAccountConfirmV316" type="checkbox" style="margin-top:4px"><span style="font-size:9px;line-height:1.7">أفهم أنني أطلب حذف حسابي والبيانات المرتبطة به وفق سياسة الخصوصية.</span></label><div class="actions"><button class="btn ghost" onclick="window.open(\'/privacy\',\'_blank\')">سياسة الخصوصية</button><button class="btn danger" onclick="submitAccountDeletionV316(event)">إرسال طلب الحذف</button></div>');
  };

  window.submitAccountDeletionV316=async function(ev){
    if(!document.getElementById('deleteAccountConfirmV316')?.checked)return toast('أكد طلب حذف الحساب أولًا');
    const btn=ev?.currentTarget;if(btn?.disabled)return;if(btn){btn.disabled=true;btn.textContent='جاري الإرسال…'}
    const payload={request_type:'delete',details:'طلب حذف الحساب من خيار حذف الحساب داخل مِنجاز.',idempotency_key:'delete-app-'+(crypto.randomUUID?.()||Date.now().toString(36))};
    try{
      const x=await api('/api/v1/privacy/requests',{method:'POST',body:JSON.stringify(payload)});
      if(x.r.ok||x.j?.error==='active_request_exists'){closeModal();toast(x.j?.error==='active_request_exists'?'طلب الحذف قيد المعالجة بالفعل':'تم تسجيل طلب حذف الحساب');await renderAccount();return}
      toast(x.j?.error==='privacy_rate_limited'?'وصلت للحد اليومي لطلبات الخصوصية':'تعذر تسجيل طلب الحذف');
    }catch(_){toast('تعذر تسجيل طلب الحذف الآن')}
    finally{if(btn){btn.disabled=false;btn.textContent='إرسال طلب الحذف'}}
  };

  async function appendStorePrivacy(){
    if(!window.me?.user)return;
    const host=document.getElementById('account');if(!host||host.querySelector('[data-store-privacy-v316]'))return;
    const active=await existingDeletion();
    const sec=document.createElement('div');sec.dataset.storePrivacyV316='1';
    sec.innerHTML='<div class="sectionHead"><div><h2>الخصوصية وحذف الحساب</h2><p>تحكم واضح في بياناتك وحسابك.</p></div></div><div class="grid two"><div class="card"><b>سياسة الخصوصية</b><p style="font-size:9px;color:#64748b;line-height:1.7">تعرف على البيانات التي نعالجها وأسباب استخدامها وخياراتك.</p><a class="btn ghost" href="/privacy" target="_blank" rel="noopener">عرض السياسة</a></div><div class="card" style="border-color:#fecaca"><b style="color:#b91c1c">حذف الحساب</b><p style="font-size:9px;color:#64748b;line-height:1.7">'+(active?'عندك طلب حذف حساب قيد المعالجة.':'تقدر تبدأ طلب حذف حسابك والبيانات المرتبطة به من هنا مباشرة.')+'</p><button class="btn '+(active?'ghost':'danger')+'" onclick="openAccountDeletionV316()">'+(active?'عرض حالة الطلب':'طلب حذف الحساب')+'</button></div></div>';
    host.appendChild(sec);
  }

  const accountBase=window.renderAccount;
  if(typeof accountBase==='function')window.renderAccount=async function(){
    await accountBase.apply(this,arguments);
    await appendStorePrivacy();
    productionText();
  };

  const bootBase=window.boot;
  if(typeof bootBase==='function')window.boot=async function(){
    await bootBase.apply(this,arguments);
    await publicConfig();productionText();
    if(deleteIntent&&window.me?.user){
      try{await go('account');setTimeout(()=>openAccountDeletionV316(),150)}catch(_){}
    }
  };

  publicConfig().then(()=>productionText());
})();
