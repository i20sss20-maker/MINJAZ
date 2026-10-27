(function(){
"use strict";
const $=id=>document.getElementById(id);
let currentUser=null,currentTasks=[],currentOrders=[],legalInfo=null,documents=[],pendingTaskKey="",loading=false;
const ERROR={
 unauthorized:"انتهت جلستك. سجّل الدخول مجددًا.",
 legal_acceptance_required:"راجع مستندات الشروط والخصوصية ووافق عليها قبل تنفيذ الطلب.",
 invalid_category:"اختر قسمًا متاحًا.",
 invalid_price:"اكتب سعرًا صحيحًا.",
 invalid_budget:"راجع الميزانية.",
 invalid_budget_range:"الحد الأعلى أقل من الحد الأدنى.",
 budget_below_minimum:"الحد الأدنى للمهمة 49 ريالًا.",
 invalid_proposal_terms:"راجع مدة التسليم والتعديلات.",
 proposal_locked:"هذا العرض مغلق.",
 task_not_found:"المهمة لم تعد متاحة.",
 invalid_credentials:"بيانات الدخول غير صحيحة.",
 insufficient_permissions:"هذه العملية غير متاحة لدورك.",
 interaction_restricted:"العملية موقوفة لحماية الأطراف.",
 task_rate_limited:"تم الوصول للحد المسموح لإنشاء المهام، حاول لاحقًا.",
 proposal_rate_limited:"تم الوصول للحد المسموح للعروض، حاول لاحقًا."
};
const money=value=>Number(value||0).toLocaleString("ar-SA",{maximumFractionDigits:2})+" ر.س";
const esc=value=>String(value===undefined||value===null?"":value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
function show(id,yes){$(id).classList.toggle("hidden",!yes)}
function notice(msg,type){const n=$("notice");n.textContent=msg;n.className="notice "+(type||"");n.classList.toggle("hidden",!msg)}
async function request(path,options={}){
 const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),12000);
 try{
  const response=await fetch(path,{method:options.method||"GET",credentials:"same-origin",cache:"no-store",
   headers:{"Accept":"application/json",...(options.data?{"Content-Type":"application/json"}:{})},
   body:options.data?JSON.stringify(options.data):undefined,signal:ctl.signal});
  const data=await response.json().catch(()=>({}));
  if(!response.ok){
   const e=new Error(ERROR[data.error]||data.error||("حدث خطأ في الخادم ("+response.status+")"));
   e.code=data.error;e.status=response.status;e.data=data;throw e;
  }
  return data;
 }catch(e){
  if(e.name==="AbortError")throw Error("انتهت مهلة الاتصال، حاول مرة أخرى.");
  if(e instanceof TypeError)throw Error("تعذر الاتصال بالسيرفر، تحقق من الشبكة.");
  throw e;
 }finally{clearTimeout(timer)}
}
function loadingButton(form,enabled){
 const b=form.querySelector('button[type="submit"]');if(b)b.disabled=enabled;
}
function humanStatus(v){
 return {open:"مفتوحة",matched:"اختير عرض",awaiting_payment:"بانتظار الدفع",in_progress:"قيد التنفيذ",delivered:"تم التسليم",completed:"مكتملة",cancelled:"ملغاة",revision_requested:"تعديل مطلوب",disputed:"نزاع"}[v]||String(v||"جديد");
}
function empty(text){return '<div class="empty">'+esc(text)+'</div>'}
function entry(title,description,meta,buttonHtml){
 return '<article class="item"><strong>'+esc(title)+'</strong><p>'+esc(description||"")+'</p><div class="item-meta">'+meta.map(x=>'<span class="chip">'+esc(x)+'</span>').join("")+'</div>'+
  (buttonHtml?'<div class="item-actions">'+buttonHtml+'</div>':"")+'</article>';
}
function showRole(){
 const u=currentUser||{},role=u.role;
 $("welcome").textContent="أهلًا، "+(u.name||"بك");
 $("who").textContent=role==="client"?"مساحة العميل · من تقديم الطلب إلى متابعة التنفيذ":role==="freelancer"?"مساحة المستقل · فرص جديدة، عروضك، وأعمالك":"لوحة الإدارة · حالة التشغيل والمتابعة";
 $("myName").value=u.name||"";
 $("myEmail").value=u.email||"";
 show("clientAction",role==="client");show("freelancerAction",role==="freelancer");show("adminAction",role==="admin");
 show("freelancerProfile",role==="freelancer");
 const switcher=$("switchRole");
 show("switchRole",role!=="admin");
 switcher.textContent=role==="client"?"العمل كمستقل":role==="freelancer"?"العمل كعميل":"";
 $("mainTitle").textContent=role==="client"?"انشر مهمة جديدة":role==="freelancer"?"ابدأ استقبال العروض":"إدارة الخدمات";
 $("mainSubtitle").textContent=role==="client"?"صف مشروعك وسيتمكن المستقلون المناسبون من تقديم عروضهم.":role==="freelancer"?"حدّث ملفك المهني من الأسفل ثم قدّم على مهمة مناسبة.":"التقارير الحساسة لا تظهر إلا للحساب الإداري المخوّل.";
 $("tasksTitle").textContent=role==="client"?"مهامي المنشورة":role==="freelancer"?"فرص العمل المتاحة":"طلبات المنصة";
 $("tasksSubtitle").textContent=role==="client"?"يمكنك عرض العروض المقدمة لكل مهمة.":role==="freelancer"?"قدّم عرضًا واضحًا للعميل، وسيتم حفظه فعليًا.":"بيانات مجمعة دون تعديل مباشر.";
 $("sideTitle").textContent=role==="admin"?"مؤشرات التشغيل":"الإشعارات";
 $("sideSubtitle").textContent=role==="admin"?"الاطلاع فقط على أهم المؤشرات.":"آخر التحديثات الخاصة بحسابك.";
}
async function renderLegal(){
 const node=$("legalWrap");if(!legalInfo||legalInfo.complete||currentUser?.role==="admin"){node.classList.add("hidden");return}
 const pending=(documents||[]).filter(d=>!legalInfo.documents?.[d.key]?.accepted);
 const rows=pending.map(d=>'<label><input type="checkbox" name="consent" value="'+esc(d.key)+'"><span><strong>'+esc(d.title)+'</strong> · النسخة '+esc(d.version)+
 '<small>'+esc((d.sections||[]).join(" · "))+(d.review_status!=="approved"?" · مسودة Beta تحتاج مراجعة قانونية.":"")+'</small></span></label>').join("");
 $("legalDocs").innerHTML=rows||empty("لا يوجد مستندات للمراجعة.");
 node.classList.remove("hidden");
}
async function loadCategories(){
 const r=await request("/api/v1/categories");
 $("categories").innerHTML='<option value="">اختر القسم</option>'+(r.items||[]).map(c=>'<option value="'+Number(c.id)+'">'+esc(c.name_ar)+'</option>').join("");
}
function renderTasks(){
 const role=currentUser.role;
 if(role==="admin"){$("taskItems").innerHTML=empty("تتوفر تفاصيل المهام من الواجهة الإدارية الكاملة.");return}
 $("taskItems").innerHTML=currentTasks.length?currentTasks.slice(0,40).map(t=>{
  const canOffer=role==="freelancer"&&t.status==="open"&&!t.has_proposal;
  const mine=role==="client";
  const actions=mine?'<button type="button" data-action="show-offers" data-id="'+Number(t.id)+'">عرض العروض ('+Number(t.proposal_count||0)+')</button>':
   canOffer?'<button type="button" data-action="new-offer" data-id="'+Number(t.id)+'">قدّم عرضًا</button>':
    (t.has_proposal?'<span class="chip">قدّمت عرضًا</span>':"");
  return entry(t.title,t.description,[humanStatus(t.status),t.category_name||t.category_slug||"مهمة",(t.budget_min?money(t.budget_min):"السعر حسب الاتفاق")],actions);
 }).join(""):empty(role==="client"?"ما عندك مهام إلى الآن. ابدأ بنشر أول مهمة من النموذج أعلاه.":"لا توجد فرص عمل متاحة في الوقت الحالي.");
}
function renderOrders(){
 const role=currentUser.role;
 if(role==="admin"){$("orderItems").innerHTML=empty("راجع طلبات العملاء من لوحة إدارة الخدمات.");return}
 $("orderItems").innerHTML=currentOrders.length?currentOrders.slice(0,25).map(o=>
 entry(o.title||("طلب #"+o.id),role==="client"?(o.freelancer_name||"المستقل"):(o.client_name||"العميل"),
 [humanStatus(o.status),money(o.amount),o.payment_status==="paid"?"مدفوع":o.payment_status==="unpaid"?"غير مدفوع":(o.payment_status||"")],"")
 ).join(""):empty("لا توجد طلبات مكتملة المطابقة حتى الآن. تتكوّن الطلبات بعد اختيار عرض مناسب.");
}
async function loadAdmin(){
 const result=await request("/api/admin/summary");
 $("summary").innerHTML=[
  ["الحسابات",result.users],["المهام",result.tasks],["الطلبات",result.orders],["تذاكر مفتوحة",result.open_support]
 ].map(p=>'<article><b>'+Number(p[1]||0)+'</b><small>'+esc(p[0])+'</small></article>').join("");
 $("sideItems").innerHTML=entry("حالات تحتاج مراجعة","ملخص الإدارة فقط",["النزاعات: "+Number(result.open_disputes||0),"طلبات الخصوصية: "+Number(result.pending_privacy||0)],"");
 renderTasks();renderOrders();
}
async function loadUserData(){
 const role=currentUser.role;
 if(role==="admin"){await loadAdmin();return}
 const [t,o,n]=await Promise.allSettled([
  request("/api/v1/tasks"),
  request("/api/v1/orders"),
  request("/api/v1/notifications?limit=8")
 ]);
 if(t.status==="fulfilled"){currentTasks=t.value.items||[]}
 else{currentTasks=[];notice("تعذر تحميل المهام: "+t.reason.message,"error")}
 if(o.status==="fulfilled"){currentOrders=o.value.items||[]}
 else{currentOrders=[];notice("تعذر تحميل الطلبات: "+o.reason.message,"error")}
 renderTasks();renderOrders();
 if(n.status==="fulfilled"){
  const data=n.value;
  $("sideItems").innerHTML=(data.items||[]).length?
  data.items.map(it=>entry(it.title,it.body,[(it.read_at?"مقروء":"جديد"),it.kind],"")).join(""):
  empty("ما عندك إشعارات جديدة.");
 }else{$("sideItems").innerHTML=empty("تعذر تحميل الإشعارات. جرّب تحديث الصفحة.")}
 const open=role==="client"?currentTasks.filter(x=>x.status==="open").length:currentTasks.filter(x=>!x.has_proposal).length;
 $("summary").innerHTML=[
  [role==="client"?"مهامي":"الفرص",currentTasks.length],
  [role==="client"?"المهام المفتوحة":"تستقبل عروضًا",open],
  ["الطلبات",currentOrders.length],
  ["الإشعارات",n.status==="fulfilled"?Number(n.value.unread||0):"—"]
 ].map(p=>'<article><b>'+esc(p[1])+'</b><small>'+esc(p[0])+'</small></article>').join("");
 const profile=$("freelancerProfile");
 if(role==="freelancer"&&profile){
  const p=window.__freelancerProfile||{};
  $("freelancerBio").value=p.bio||"";
  $("freelancerSkills").value=(p.skills||[]).join("، ");
  $("available").checked=Boolean(p.is_available);
 }
}
async function load(){
 if(loading)return;loading=true;
 $("loading").classList.remove("hidden");
 try{
  const me=await request("/api/v1/me");
  if(!me.user){throw Error("تعذر معرفة صاحب الجلسة.")}
  currentUser=me.user;
  window.__freelancerProfile=me.freelancer_profile||{};
  show("workspace",true);show("loginRequired",false);show("logout",true);
  showRole();
  const results=await Promise.allSettled([
   request("/api/v1/legal/status"),request("/api/v1/legal/documents"),loadCategories()
  ]);
  legalInfo=results[0].status==="fulfilled"?results[0].value:null;
  documents=results[1].status==="fulfilled"?results[1].value.documents||[]:[];
  await renderLegal();
  await loadUserData();
 }catch(e){
  show("workspace",false);
  show("loginRequired",true);
  show("logout",false);
  notice(e.status===401?"انتهت الجلسة، ادخل من جديد.":e.message,e.status===401?"":"error");
 }finally{$("loading").classList.add("hidden");loading=false}
}
$("switchRole").addEventListener("click",async()=>{
 if(!currentUser||currentUser.role==="admin")return;
 const target=currentUser.role==="client"?"freelancer":"client";
 const btn=$("switchRole");btn.disabled=true;
 try{
  await request("/api/v1/me/active-role",{method:"PATCH",data:{role:target}});
  notice("تم تغيير وضع الحساب بنجاح.","success");await load();
 }catch(e){notice(e.message,"error")}finally{btn.disabled=false}
});
$("logout").addEventListener("click",async()=>{
 const b=$("logout");b.disabled=true;
 try{await request("/api/v1/auth/logout",{method:"POST"});location.assign("/signup?auth=login")}
 catch(e){notice(e.message,"error");b.disabled=false}
});
$("acceptLegal").addEventListener("click",async()=>{
 const missing=documents.filter(d=>!legalInfo?.documents?.[d.key]?.accepted).map(d=>d.key);
 const checked=[...$("legalDocs").querySelectorAll('input[type="checkbox"]:checked')].map(x=>x.value);
 if(!missing.length)return;
 if(missing.some(x=>!checked.includes(x))){notice("اقرأ المستندات وحدّد جميع الإصدارات المطلوبة للموافقة.","error");return}
 const btn=$("acceptLegal");btn.disabled=true;
 try{legalInfo=await request("/api/v1/legal/accept",{method:"POST",data:{documents:checked}});await renderLegal();notice("تم حفظ الموافقة على مستندات النسخة التجريبية.","success")}
 catch(e){notice(e.message,"error")}finally{btn.disabled=false}
});
$("newTask").addEventListener("submit",async e=>{
 e.preventDefault();
 const form=e.currentTarget,fd=new FormData(form);loadingButton(form,true);
 const budget_min=fd.get("budget_min"),budget_max=fd.get("budget_max");
 const payload={title:String(fd.get("title")||"").trim(),description:String(fd.get("description")||"").trim(),
  category_id:Number(fd.get("category_id")),budget_min:budget_min?Number(budget_min):null,
  budget_max:budget_max?Number(budget_max):null,
  idempotency_key:pendingTaskKey||(pendingTaskKey="work-"+(crypto.randomUUID?.()||Date.now().toString(36)+"-"+Math.random().toString(36).slice(2)))};
 try{
  await request("/api/v1/tasks",{method:"POST",data:payload});
  pendingTaskKey="";form.reset();notice("تم نشر المهمة في حسابك، ويمكن للمستقلين تقديم عروضهم.","success");await loadUserData()
 }catch(err){
  if(err.code==="idempotency_key_reused")pendingTaskKey="";
  notice(err.message,"error");
  if(err.code==="legal_acceptance_required")$("legalWrap").scrollIntoView({behavior:"smooth"});
 }finally{loadingButton(form,false)}
});
$("taskItems").addEventListener("click",async e=>{
 const b=e.target.closest("button[data-action]");if(!b)return;
 const id=Number(b.dataset.id);
 if(!Number.isSafeInteger(id)||id<1)return;
 if(b.dataset.action==="new-offer"){
  const task=currentTasks.find(t=>Number(t.id)===id);
  if(!task)return;
  $("offerTaskTitle").textContent=task.title;
  $("offerTaskId").value=String(id);
  $("offerDialog").showModal();
 }else if(b.dataset.action==="show-offers"){
  b.disabled=true;
  try{
   const resp=await request("/api/v1/tasks/"+id+"/proposals");
   $("receivedOffers").innerHTML=(resp.items||[]).length?
    resp.items.map(p=>entry(p.name||"مستقل",p.message,["السعر: "+money(p.price),"التسليم: "+Number(p.delivery_hours)+" س","التعديلات: "+Number(p.revisions||0)],"")).join(""):empty("لم تصل عروض لهذه المهمة بعد.");
   $("offersDialog").showModal()
  }catch(err){notice(err.message,"error")}finally{b.disabled=false}
 }
});
$("offerForm").addEventListener("submit",async e=>{
 e.preventDefault();const f=e.currentTarget,fd=new FormData(f),task_id=Number(fd.get("task_id"));loadingButton(f,true);
 try{
  await request("/api/v1/tasks/"+task_id+"/proposals",{method:"POST",data:{
   price:Number(fd.get("price")),delivery_hours:Number(fd.get("delivery_hours")),revisions:Number(fd.get("revisions")),message:String(fd.get("message")||"").trim()
  }});
  $("offerDialog").close();f.reset();notice("تم إرسال عرضك للعميل بنجاح.","success");await loadUserData();
 }catch(err){notice(err.message,"error");$("offerDialog").close();if(err.code==="legal_acceptance_required")$("legalWrap").scrollIntoView({behavior:"smooth"})}
 finally{loadingButton(f,false)}
});
$("closeOffer").addEventListener("click",()=>$("offerDialog").close());
$("closeOffers").addEventListener("click",()=>$("offersDialog").close());
$("nameForm").addEventListener("submit",async e=>{
 e.preventDefault();const f=e.currentTarget;loadingButton(f,true);
 try{
  await request("/api/v1/me/profile",{method:"PATCH",data:{name:$("myName").value.trim()}});
  notice("تم تحديث اسم حسابك.","success");await load()
 }catch(err){notice(err.message,"error")}finally{loadingButton(f,false)}
});
$("freelancerProfile").addEventListener("submit",async e=>{
 e.preventDefault();const f=e.currentTarget;loadingButton(f,true);
 try{
  const skills=$("freelancerSkills").value.split(/[,،]/).map(x=>x.trim()).filter(Boolean).slice(0,30);
  window.__freelancerProfile=await request("/api/v1/freelancer/profile",{method:"PATCH",data:{
   bio:$("freelancerBio").value.trim(),skills,is_available:$("available").checked
  }});
  notice("تم حفظ ملف المستقل والمهارات.","success")
 }catch(err){notice(err.message,"error")}finally{loadingButton(f,false)}
});
load();
})();