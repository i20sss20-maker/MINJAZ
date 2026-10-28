(function(){
"use strict";
const $=id=>document.getElementById(id);
let currentUser=null,currentTasks=[],currentOrders=[],currentProposals=[],legalInfo=null,documents=[],pendingTaskKey="",pendingMessageKey="",activeOrderId=0,activeOfferTaskId=0,loading=false;
const loadErrors={tasks:false,orders:false,proposals:false};
const TASK_PAGE_SIZE=20,ORDER_PAGE_SIZE=15;
let taskVisibleCount=TASK_PAGE_SIZE,orderVisibleCount=ORDER_PAGE_SIZE;
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
 proposal_rate_limited:"تم الوصول للحد المسموح للعروض، حاول لاحقًا.",
 order_exists:"سبق اختيار عرض لهذه المهمة.",
 proposal_not_available:"العرض لم يعد متاحًا للاختيار.",
 message_rate_limited:"وصلت للحد المسموح للرسائل خلال ساعة.",
 idempotency_key_reused:"تم تغيير الطلب بعد محاولة سابقة، راجع البيانات وحاول مجددًا.",
 task_not_open:"المهمة ليست مفتوحة الآن.",
 task_has_order:"سبق اختيار مستقل لهذه المهمة، ولا يمكن إغلاقها بهذه الطريقة."
};
const money=value=>Number(value||0).toLocaleString("ar-SA",{maximumFractionDigits:2})+" ر.س";
const esc=value=>String(value===undefined||value===null?"":value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
function show(id,yes){$(id).classList.toggle("hidden",!yes)}
let toastTimer=null;
function notice(msg,type){
 const n=$("notice"),toast=$("actionToast"),text=String(msg||"");
 n.textContent=text;n.className="notice "+(type||"");n.classList.toggle("hidden",!text);
 clearTimeout(toastTimer);toast.textContent=text;toast.className="action-toast"+(type?" "+type:"");
 toast.classList.toggle("visible",Boolean(text));
 if(text)toastTimer=setTimeout(()=>toast.classList.remove("visible"),type==="error"?8500:5200);
}
async function request(path,options={}){
 const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),options.timeoutMs||12000);
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

const MAX_ATTACHMENT_BYTES=10_000_000;
const ACCEPTED_ATTACHMENT_MIME={
 ".pdf":"application/pdf", ".doc":"application/msword",
 ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
 ".xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
 ".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg",
 ".webp":"image/webp", ".zip":"application/zip"
};
let stagedTaskAttachments=null,stagedMessageAttachments=null;
async function uploadRealAttachments(list,statusNode){
 const files=Array.from(list||[]);
 if(!files.length){statusNode.textContent="لا توجد مرفقات مضافة.";return []}
 if(files.length>3)throw Error("يسمح بإرفاق ثلاثة ملفات كحد أقصى.");
 const result=[];
 for(let i=0;i<files.length;i++){
  const file=files[i],ext="."+String(file.name).split(".").pop().toLowerCase();
  if(!Object.hasOwn(ACCEPTED_ATTACHMENT_MIME,ext))throw Error("نوع ملف غير مسموح: "+file.name);
  if(!file.size||file.size>MAX_ATTACHMENT_BYTES)throw Error("حجم الملف يجب أن يكون بين 1 بايت و10 ميجابايت: "+file.name);
  const type=file.type||ACCEPTED_ATTACHMENT_MIME[ext];
  statusNode.textContent="جاري رفع ملف "+(i+1)+" من "+files.length+": "+file.name;
  const signed=await request("/api/v1/uploads/presign",{method:"POST",data:{
   file_name:file.name,mime_type:type,size_bytes:file.size
  },timeoutMs:30000});
  if(!signed.upload_url||!signed.key)throw Error("تعذر تجهيز رابط الرفع الخاص.");
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),65000);
  let response;
  try{
   response=await fetch(signed.upload_url,{
    method:"PUT",mode:"cors",cache:"no-store",headers:signed.headers||{"Content-Type":type},
    body:file,signal:ctl.signal
   });
  }catch(err){
   throw Error("فشل رفع الملف إلى مساحة التخزين الخاصة؛ تحقق من الشبكة أو إعدادات CORS.");
  }finally{clearTimeout(timer)}
  if(!response.ok)throw Error("تعذر رفع الملف إلى التخزين ("+response.status+").");
  const verified=await request("/api/v1/uploads/complete",{method:"POST",
   data:{key:signed.key},timeoutMs:30000});
  if(!verified.attachment||verified.attachment.storage_key!==signed.key){
   throw Error("تعذر التأكد من حفظ الملف. لم يُرسل الطلب.");
  }
  result.push(verified.attachment);
 }
 statusNode.textContent="اكتمل رفع "+result.length+" ملف إلى التخزين الخاص.";
 return result;
}
function attachmentLinks(items){
 return (items||[]).map(att=>{
  const raw=String(att.file_url||att.url||"");
  let safe=false;
  try{const u=new URL(raw);safe=u.protocol==="https:"&&!u.username&&!u.password}
  catch(err){}
  if(!safe)return "";
  return '<a class="btn-lite" href="'+esc(raw)+'" target="_blank" rel="noopener noreferrer">'+
   esc(att.file_name||att.name||"مرفق محفوظ")+'</a>';
 }).join("");
}
function humanStatus(v){
 return {open:"مفتوحة",matched:"اختير عرض",awaiting_payment:"بانتظار الدفع",in_progress:"قيد التنفيذ",delivered:"تم التسليم",completed:"مكتملة",cancelled:"ملغاة",revision_requested:"تعديل مطلوب",disputed:"نزاع"}[v]||String(v||"جديد");
}
function normalizeSearch(value){
 return String(value||"").toLocaleLowerCase("ar").normalize("NFKC")
  .replace(/[\u064b-\u065f\u0670\u0640]/g,"").replace(/[أإآ]/g,"ا")
  .replace(/ى/g,"ي").replace(/ة/g,"ه").replace(/\s+/g," ").trim();
}
function matchesSearch(query,values){
 const q=normalizeSearch(query);
 return !q||normalizeSearch(values.join(" ")).includes(q);
}
function updateListCount(nodeId,shown,total,label,matching){
 const result=matching===undefined?shown:matching;
 $(nodeId).textContent=total===0?"لا توجد "+label+" حاليًا":
  result===0?"لا توجد نتائج مطابقة في "+label:
  "عرض "+shown+" من أصل "+total+" "+label+(result>shown?" · يمكنك عرض المزيد":"");
}
function setTaskFilterOptions(role){
 const input=$("taskStatusFilter");
 const options=role==="freelancer"?
  [["all","كل فرص العمل"],["not-offered","لم أقدّم عليها"],["offered","قدّمت عرضًا"]]:
  [["all","كل المشاريع"],["open","تستقبل عروضًا"],["matched","تم اختيار مستقل"],["closed","مغلقة"]];
 input.replaceChildren();
 options.forEach(([value,label])=>{
  const option=document.createElement("option");option.value=value;option.textContent=label;input.append(option);
 });
}
function filteredTasks(){
 const term=$("taskSearch").value,choice=$("taskStatusFilter").value,role=currentUser.role;
 return currentTasks.filter(t=>{
  if(!matchesSearch(term,[t.title,t.description,t.category_name,t.category_slug]))return false;
  if(choice==="all")return true;
  if(role==="freelancer")return choice==="offered"?Boolean(t.has_proposal):!t.has_proposal;
  return t.status===choice;
 });
}
function filteredOrders(){
 const term=$("orderSearch").value,choice=$("orderStatusFilter").value;
 return currentOrders.filter(o=>
  (choice==="all"||o.status===choice)&&
  matchesSearch(term,[o.title,o.client_name,o.freelancer_name,String(o.id||"")])
 );
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
 show("navCreate",role==="client");show("navProposals",role==="freelancer");
 show("taskTools",role!=="admin");show("orderTools",role!=="admin");
 setTaskFilterOptions(role);
 $("taskSearch").value="";$("orderSearch").value="";
 $("orderStatusFilter").value="all";taskVisibleCount=TASK_PAGE_SIZE;orderVisibleCount=ORDER_PAGE_SIZE;
 show("freelancerProfile",role==="freelancer");show("clientProfile",role==="client");show("proposalPanel",role==="freelancer");show("markAllRead",role!=="admin");
 show("portfolioPanel",role==="freelancer");show("adminQueuesPanel",role==="admin");show("launchReadinessPanel",role==="admin");
 show("ownerAdminPanel",Boolean(u.admin_eligible));
 if(role==="freelancer")$("kycStatus").textContent=(window.__freelancerProfile?.kyc_status==="approved")?"الهوية موثّقة لدى المزود":"الهوية غير معتمدة. لن تظهر شارة موثّق قبل اكتمال تحقق فعلي."
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
 if(role==="admin"){$("taskItems").innerHTML=empty("تتوفر تفاصيل المهام من الواجهة الإدارية الكاملة.");$("tasksResultCount").textContent="";show("moreTasks",false);return}
 if(loadErrors.tasks){$("taskItems").innerHTML=empty("تعذّر الاتصال بالمشاريع الآن. اضغط تحديث البيانات للمحاولة مجددًا.");$("tasksResultCount").textContent="البيانات غير متاحة مؤقتًا";show("moreTasks",false);return}
 const tasks=filteredTasks();
 updateListCount("tasksResultCount",Math.min(taskVisibleCount,tasks.length),currentTasks.length,"المشاريع",tasks.length);
 show("moreTasks",tasks.length>taskVisibleCount);
 $("taskItems").innerHTML=tasks.length?tasks.slice(0,taskVisibleCount).map(t=>{
  const canOffer=role==="freelancer"&&t.status==="open"&&!t.has_proposal;
  const mine=role==="client";
  const actions=mine?'<button type="button" data-action="show-offers" data-id="'+Number(t.id)+'">عرض العروض ('+Number(t.proposal_count||0)+')</button>'+(t.status==="open"?'<button type="button" data-action="close-task" data-id="'+Number(t.id)+'">إغلاق المهمة</button>':""):
   canOffer?'<button type="button" data-action="new-offer" data-id="'+Number(t.id)+'">قدّم عرضًا</button>':
    (t.has_proposal?'<span class="chip">قدّمت عرضًا</span>':"");
  const fullActions=role==="freelancer"?actions+'<button type="button" data-action="report-task" data-id="'+Number(t.id)+'">إبلاغ عن المهمة</button>':actions;
  return entry(t.title,t.description,[humanStatus(t.status),t.category_name||t.category_slug||"مهمة",(t.budget_min?money(t.budget_min):"السعر حسب الاتفاق")],fullActions);
 }).join(""):empty(currentTasks.length?"لا توجد مشاريع مطابقة للبحث أو التصفية. جرّب تغيير الكلمات أو الحالة.":role==="client"?"ما نشرت مشاريع بعد. ابدأ بنشر أول مشروع من النموذج أعلاه.":"لا توجد فرص عمل متاحة في الوقت الحالي.");
}
function renderOrders(){
 const role=currentUser.role;
 if(role==="admin"){$("orderItems").innerHTML=empty("راجع طلبات العملاء من لوحة إدارة الخدمات.");$("ordersResultCount").textContent="";show("moreOrders",false);return}
 if(loadErrors.orders){$("orderItems").innerHTML=empty("تعذّر تحميل طلباتك الآن. اضغط تحديث البيانات للمحاولة مجددًا.");$("ordersResultCount").textContent="البيانات غير متاحة مؤقتًا";show("moreOrders",false);return}
 const orders=filteredOrders();
 updateListCount("ordersResultCount",Math.min(orderVisibleCount,orders.length),currentOrders.length,"الطلبات",orders.length);
 show("moreOrders",orders.length>orderVisibleCount);
 $("orderItems").innerHTML=orders.length?orders.slice(0,orderVisibleCount).map(o=>
  entry(o.title||("طلب #"+o.id),role==="client"?(o.freelancer_name||"المستقل"):(o.client_name||"العميل"),
  [humanStatus(o.status),money(o.amount),o.payment_status==="paid"?"الدفع مؤكد":o.payment_status==="unpaid"?"لم يُدفع":(o.payment_status||"")],
  '<button type="button" data-action="open-order" data-id="'+Number(o.id)+'">المحادثة والتفاصيل</button>')
 ).join(""):empty(currentOrders.length?"لا توجد طلبات مطابقة للبحث أو التصفية.":"لا توجد طلبات بعد. عندما تختار عرضًا محفوظًا يصبح الطلب بانتظار الدفع المعتمد.");
}
function renderProposals(){
 if(loadErrors.proposals){$("proposalItems").innerHTML=empty("تعذّر تحميل عروضك الآن. جرّب تحديث البيانات.");return}
 $("proposalItems").innerHTML=currentProposals.length?currentProposals.slice(0,60).map(p=>{
  const canWithdraw=p.proposal_status==="sent"&&p.task_status==="open"&&!p.order_id;
  const meta=[p.proposal_status==="sent"?"بانتظار رد العميل":p.proposal_status==="accepted"?"تم اختيار عرضك":p.proposal_status==="rejected"?"لم يتم اختيار العرض":p.proposal_status||"عرض",
   money(p.price),"التسليم "+Number(p.delivery_hours||0)+" ساعة"];
  if(p.order_id)meta.push("الطلب: "+humanStatus(p.order_status));
  const action=canWithdraw?'<button type="button" data-action="withdraw-offer" data-id="'+Number(p.task_id)+'">سحب العرض</button>':"";
  return entry(p.title||("مهمة #"+p.task_id),p.message||p.description,meta,action);
 }).join(""):empty("لم ترسل عروضًا بعد. تصفح الفرص المتاحة وقدّم على مشروع مناسب.");
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
 const [t,o,n,proposals,profileResult]=await Promise.allSettled([
  request("/api/v1/tasks"),
  request("/api/v1/orders"),
  request("/api/v1/notifications?limit=8"),
  role==="freelancer"?request("/api/v1/freelancer/proposals"):Promise.resolve({items:[]}),
  role==="client"?request("/api/v1/client/profile"):Promise.resolve(null)
 ]);
 loadErrors.tasks=t.status!=="fulfilled";
 if(!loadErrors.tasks)currentTasks=t.value.items||[];
 else{currentTasks=[];notice("تعذر تحميل المشاريع: "+t.reason.message,"error")}
 loadErrors.orders=o.status!=="fulfilled";
 if(!loadErrors.orders)currentOrders=o.value.items||[];
 else{currentOrders=[];notice("تعذر تحميل الطلبات: "+o.reason.message,"error")}
 renderTasks();renderOrders();
 loadErrors.proposals=proposals.status!=="fulfilled";
 currentProposals=loadErrors.proposals?[]:(proposals.value.items||[]);
 if(role==="freelancer"){renderProposals();if(proposals.status==="rejected")notice("تعذر تحميل عروضك: "+proposals.reason.message,"error")}
 if(role==="client"&&profileResult.status==="fulfilled"&&profileResult.value){
  const c=profileResult.value;$("clientCompany").value=c.company_name||"";$("clientCity").value=c.city||"";
  $("clientSector").value=c.sector||"";$("clientBio").value=c.bio||"";
 }
 if(n.status==="fulfilled"){
  const data=n.value;
  show("markAllRead",Number(data.unread||0)>0);
  $("sideItems").innerHTML=(data.items||[]).length?
  data.items.map(it=>entry(it.title,it.body,[(it.read_at?"مقروء":"جديد"),it.kind],"")).join(""):
  empty("ما عندك إشعارات جديدة.");
 }else{$("sideItems").innerHTML=empty("تعذر تحميل الإشعارات. جرّب تحديث الصفحة.");show("markAllRead",false)}
 const open=role==="client"?currentTasks.filter(x=>x.status==="open").length:currentTasks.filter(x=>!x.has_proposal).length;
 $("summary").innerHTML=[
  [role==="client"?"مشاريعي":"الفرص",loadErrors.tasks?"—":currentTasks.length],
  [role==="client"?"المشاريع المفتوحة":"فرص جديدة",loadErrors.tasks?"—":open],
  ["الطلبات",loadErrors.orders?"—":currentOrders.length],
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
 $("workspace").setAttribute("aria-busy","true");
 $("refreshWorkspace").disabled=true;
 try{
  const me=await request("/api/v1/me");
  if(!me.user){throw Error("تعذر معرفة صاحب الجلسة.")}
  currentUser=me.user;
  window.__freelancerProfile=me.freelancer_profile||{};
  show("workspace",true);show("loginRequired",false);show("logout",true);
  showRole();
  const hash=window.location.hash||"";
  if(hash.startsWith("#admin-claim=")){
   try{
    const token=decodeURIComponent(hash.slice("#admin-claim=".length));
    if(currentUser.admin_eligible&&/^[A-Za-z0-9_-]{35,160}$/.test(token)){
     $("ownerAdminToken").value=token;
     show("ownerAdminConfirmForm",true);
     notice("وصل رابط تأكيد الإدارة. أدخل كلمة مرورك الحالية لتفعيل الصلاحيات.","success");
    }
   }catch(e){}
   history.replaceState(null,"",location.pathname+location.search);
  }
  const results=await Promise.allSettled([
   request("/api/v1/legal/status"),request("/api/v1/legal/documents"),loadCategories()
  ]);
  legalInfo=results[0].status==="fulfilled"?results[0].value:null;
  documents=results[1].status==="fulfilled"?results[1].value.documents||[]:[];
  await renderLegal();
  await loadUserData();
  await loadExtraPanels();
 }catch(e){
  if(e.status===401)currentUser=null;
  show("workspace",Boolean(currentUser));
  show("loginRequired",!currentUser);
  show("logout",Boolean(currentUser));
  notice(e.status===401?"انتهت الجلسة، ادخل من جديد.":"تعذر تحديث مساحة العمل: "+e.message,"error");
 }finally{$("loading").classList.add("hidden");$("workspace").removeAttribute("aria-busy");$("refreshWorkspace").disabled=false;loading=false}
}
$("taskSearch").addEventListener("input",()=>{taskVisibleCount=TASK_PAGE_SIZE;if(currentUser&&currentUser.role!=="admin")renderTasks()});
$("taskStatusFilter").addEventListener("change",()=>{taskVisibleCount=TASK_PAGE_SIZE;if(currentUser&&currentUser.role!=="admin")renderTasks()});
$("orderSearch").addEventListener("input",()=>{orderVisibleCount=ORDER_PAGE_SIZE;if(currentUser&&currentUser.role!=="admin")renderOrders()});
$("orderStatusFilter").addEventListener("change",()=>{orderVisibleCount=ORDER_PAGE_SIZE;if(currentUser&&currentUser.role!=="admin")renderOrders()});
$("refreshWorkspace").addEventListener("click",()=>{if(!loading)load()});
$("moreTasks").addEventListener("click",()=>{taskVisibleCount+=TASK_PAGE_SIZE;renderTasks()});
$("moreOrders").addEventListener("click",()=>{orderVisibleCount+=ORDER_PAGE_SIZE;renderOrders()});
$("switchRole").addEventListener("click",async()=>{
 if(!currentUser||currentUser.role==="admin")return;
 const target=currentUser.role==="client"?"freelancer":"client";
 const btn=$("switchRole");btn.disabled=true;
 try{
  await request("/api/v1/me/active-role",{method:"PATCH",data:{role:target}});
  notice("تم تغيير وضع الحساب بنجاح.","success");await load();
 }catch(e){notice(e.message,"error")}finally{btn.disabled=false}
});
$("ownerAdminRequestForm").addEventListener("submit",async e=>{
 e.preventDefault();if(!currentUser?.admin_eligible)return;
 const f=e.currentTarget,pass=$("ownerAdminRequestPassword").value;
 if(pass.length<10){notice("كلمة المرور غير صالحة.","error");return}
 loadingButton(f,true);
 try{
  const r=await request("/api/v1/auth/admin-claim/request",{method:"POST",data:{password:pass}});
  $("ownerAdminRequestPassword").value="";
  if(r.already_admin){notice("هذا الحساب لديه صلاحيات الإدارة بالفعل.","success");await load();return}
  show("ownerAdminConfirmForm",true);
  notice("أرسلنا رابط تأكيد الإدارة إلى البريد الموثّق. افتحه على نفس المتصفح أو الصق الرمز هنا، ثم أعد كتابة كلمة المرور.","success");
 }catch(err){notice(err.code==="admin_claim_rate_limited"?"محاولات كثيرة، حاول لاحقًا.":err.message,"error")}
 finally{loadingButton(f,false)}
});
$("ownerAdminConfirmForm").addEventListener("submit",async e=>{
 e.preventDefault();if(!currentUser?.admin_eligible)return;
 const f=e.currentTarget,token=$("ownerAdminToken").value.trim(),password=$("ownerAdminConfirmPassword").value;
 if(!/^[A-Za-z0-9_-]{35,160}$/.test(token)||password.length<10){
  notice("تحقق من رمز البريد وكلمة المرور.","error");return;
 }
 loadingButton(f,true);
 try{
  const r=await request("/api/v1/auth/admin-claim/confirm",{method:"POST",data:{token,password}});
  $("ownerAdminConfirmPassword").value="";$("ownerAdminToken").value="";
  if(r.admin_activated){
   notice("تم تفعيل الإدارة بعد التحقق من ملكية البريد وكلمة المرور. خرجت الأجهزة الأخرى.","success");
   await load();
  }
 }catch(err){notice(err.message,"error")}
 finally{loadingButton(f,false)}
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
  if(!stagedTaskAttachments)stagedTaskAttachments=await uploadRealAttachments($("taskFiles").files,$("taskUploadStatus"));
  payload.attachments=stagedTaskAttachments;
  await request("/api/v1/tasks",{method:"POST",data:payload});
  pendingTaskKey="";stagedTaskAttachments=null;form.reset();
  $("taskUploadStatus").textContent="يمكن إرفاق ملفات إضافية في المشروع التالي.";
  notice("تم نشر المهمة ومرفقاتها المحفوظة، ويمكن للمستقلين تقديم عروضهم.","success");await loadUserData()
 }catch(err){
  if(err.code==="idempotency_key_reused")pendingTaskKey="";
  notice(err.message,"error");
  if(err.code==="legal_acceptance_required")$("legalWrap").scrollIntoView({behavior:"smooth"});
 }finally{loadingButton(form,false)}
});
$("newTask").addEventListener("input",()=>{pendingTaskKey="";stagedTaskAttachments=null});
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
   activeOfferTaskId=id;
   const task=currentTasks.find(t=>Number(t.id)===id);
   $("receivedOffers").innerHTML=(resp.items||[]).length?
    resp.items.map(p=>{
     const canSelect=task?.status==="open"&&p.status==="sent";
     const action=canSelect?'<button type="button" data-action="select-offer" data-id="'+Number(p.id)+'">اختيار العرض وإنشاء الطلب</button>':"";
     return entry(p.name||"مستقل",(p.message||"")+(p.bio?" · نبذة المستقل: "+p.bio:""),
      ["السعر: "+money(p.price),"التسليم: "+Number(p.delivery_hours)+" س",
       "التعديلات: "+Number(p.revisions||0),p.kyc_status==="approved"?"هوية معتمدة":"الهوية غير موثقة"],action);
    }).join(""):empty("لم تصل عروض لهذه المهمة بعد.");
   $("offersDialog").showModal()
  }catch(err){notice(err.message,"error")}finally{b.disabled=false}
 }else if(b.dataset.action==="close-task"){
  const task=currentTasks.find(t=>Number(t.id)===id);
  if(!task||task.status!=="open")return;
  if(!window.confirm("إغلاق المهمة سيمنع العروض الجديدة ويرفض العروض المعلقة، ولا يمكن التراجع عنه. هل أنت متأكد؟"))return;
  b.disabled=true;
  try{
   await request("/api/v1/tasks/"+id+"/close",{method:"POST",data:{}});
   notice("أغلقت المهمة وأُبلغ أصحاب العروض.","success");await loadUserData();
  }catch(err){notice(err.message,"error")}finally{b.disabled=false}
 }else if(b.dataset.action==="report-task"){
  if(currentUser.role!=="freelancer")return;
  openReportDialog({task_id:id});
 }
});
$("receivedOffers").addEventListener("click",async e=>{
 const b=e.target.closest('button[data-action="select-offer"]');if(!b)return;
 const proposalId=Number(b.dataset.id);
 const task=currentTasks.find(t=>Number(t.id)===activeOfferTaskId);
 if(!Number.isSafeInteger(proposalId)||proposalId<1||!task||task.status!=="open")return;
 if(!window.confirm("تأكيد الاختيار: سينشأ طلب حقيقي ويُغلق باب العروض. لن يُخصم أي مبلغ ولن يبدأ التنفيذ حتى تفعيل الدفع الرسمي وتسويات المستقلين. هل توافق؟"))return;
 b.disabled=true;
 try{
  const order=await request("/api/v1/orders",{method:"POST",data:{proposal_id:proposalId}});
  $("offersDialog").close();
  notice("تم اختيار العرض وإنشاء طلب #"+Number(order.id)+" بانتظار الدفع الرسمي. لم يتم تحصيل أي مبلغ.","success");
  await loadUserData();
 }catch(err){notice(err.message,"error")}finally{b.disabled=false}
});
$("proposalItems").addEventListener("click",async e=>{
 const b=e.target.closest('button[data-action="withdraw-offer"]');if(!b)return;
 const id=Number(b.dataset.id);
 if(!Number.isSafeInteger(id)||id<1||!window.confirm("هل تريد سحب هذا العرض من المهمة المفتوحة؟"))return;
 b.disabled=true;
 try{
  await request("/api/v1/tasks/"+id+"/proposals",{method:"DELETE"});
  notice("سُحب العرض من قاعدة البيانات بنجاح.","success");await loadUserData();
 }catch(err){notice(err.message,"error")}finally{b.disabled=false}
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
$("closeOrder").addEventListener("click",()=>{
 activeOrderId=0;pendingMessageKey="";stagedMessageAttachments=null;
 $("messageFiles").value="";$("messageBody").value="";$("orderDialog").close();
});
function displayDate(value){
 if(!value)return "";
 const date=new Date(value);
 return Number.isNaN(date.getTime())?"":date.toLocaleString("ar-SA",{dateStyle:"short",timeStyle:"short"});
}
async function showOrder(id,openDialog=true){
 if(!Number.isSafeInteger(id)||id<1)return;
 const [order,messages,timeline,cancel]=await Promise.all([
  request("/api/v1/orders/"+id),
  request("/api/v1/orders/"+id+"/messages"),
  request("/api/v1/orders/"+id+"/timeline"),
  request("/api/v1/orders/"+id+"/cancellation")
 ]);
 if(activeOrderId!==id){
  pendingMessageKey="";stagedMessageAttachments=null;
  $("messageFiles").value="";$("messageBody").value="";
 }
 activeOrderId=id;
 $("orderTitle").textContent=order.title||("طلب #"+id);
 $("reportOrderButton").disabled=false;
 const pending=order.status==="awaiting_payment";
 $("orderInfo").innerHTML=entry("الطلب #"+id,order.description||"",
  [humanStatus(order.status),"المبلغ المتفق عليه: "+money(order.amount),
   order.payment_status==="paid"?"الدفع مؤكد":"لم يتم دفع أي مبلغ",
   "العميل: "+(order.client_name||"-"),"المستقل: "+(order.freelancer_name||"-")],"")+
  (pending?'<div class="warning">هذا طلب حقيقي مسجّل، لكنه لا يسمح ببدء تنفيذ مدفوع قبل ربط بوابة الدفع الرسمية وتسويات المستقلين. لا ترسل أي مبالغ خارج المنصة.</div>':"");
 const currentCancel=cancel.item||null,activeCancel=currentCancel&&["pending","in_review"].includes(currentCancel.status);
 const canCancel=!["cancelled","completed","disputed"].includes(order.status)&&!activeCancel;
 show("orderCancelSection",Boolean(canCancel||currentCancel));
 show("orderCancelForm",canCancel);
 $("orderCancelInfo").innerHTML=currentCancel?
  entry("حالة طلب الإلغاء #"+Number(currentCancel.id),currentCancel.reason||"",
   [ticketStatus(currentCancel.status),"الاسترداد: "+(currentCancel.refund_status==="not_needed"?"لا توجد أموال محصّلة":currentCancel.refund_status||"مراجعة")],""):
  empty("لا يوجد طلب إلغاء سابق. أي طلب جديد يُراجع من الإدارة أولًا.");
 $("orderMessages").innerHTML=(messages.items||[]).length?(messages.items||[]).map(m=>
  entry(m.sender_name||"عضو",m.body||"مرفق",["بتاريخ "+displayDate(m.created_at)],
   attachmentLinks(m.attachments))
 ).join(""):empty("ما فيه رسائل حتى الآن. ابدأ محادثة مع الطرف الآخر.");
 $("orderTimeline").innerHTML=(timeline.items||[]).length?(timeline.items||[]).map(t=>
  entry(t.title||"تحديث",t.details||"",[displayDate(t.created_at),t.actor_name||"المنصة"],"")
 ).join(""):empty("لا توجد أحداث مسجلة.");
 if(openDialog&&!$("orderDialog").open)$("orderDialog").showModal();
}
$("orderItems").addEventListener("click",async e=>{
 const b=e.target.closest('button[data-action="open-order"]');if(!b)return;
 const id=Number(b.dataset.id);
 if(!currentOrders.some(o=>Number(o.id)===id))return;
 b.disabled=true;
 try{await showOrder(id)}catch(err){notice("تعذر فتح الطلب: "+err.message,"error")}
 finally{b.disabled=false}
});
$("refreshOrder").addEventListener("click",async()=>{
 if(!activeOrderId)return;
 const btn=$("refreshOrder");btn.disabled=true;
 try{await showOrder(activeOrderId,false)}catch(err){notice(err.message,"error")}
 finally{btn.disabled=false}
});
$("messageBody").addEventListener("input",()=>{pendingMessageKey="";stagedMessageAttachments=null});
$("messageFiles").addEventListener("change",()=>{pendingMessageKey="";stagedMessageAttachments=null});
$("messageForm").addEventListener("submit",async e=>{
 e.preventDefault();
 const id=activeOrderId,form=e.currentTarget,body=$("messageBody").value.trim();
 if(!id||!body){notice("اكتب رسالة أولًا.","error");return}
 loadingButton(form,true);
 pendingMessageKey=pendingMessageKey||"message-"+(crypto.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2));
 try{
  if(!stagedMessageAttachments)stagedMessageAttachments=await uploadRealAttachments($("messageFiles").files,$("messageUploadStatus"));
  await request("/api/v1/orders/"+id+"/messages",{method:"POST",data:{
   body,attachments:stagedMessageAttachments,idempotency_key:pendingMessageKey
  }});
  pendingMessageKey="";stagedMessageAttachments=null;$("messageBody").value="";
  $("messageFiles").value="";$("messageUploadStatus").textContent="المرفقات الجديدة تُحفظ في مساحة خاصة.";
  notice("أُرسلت الرسالة وحُفظت في محادثة الطلب.","success");
  await showOrder(id,false);
 }catch(err){
  if(err.code==="idempotency_key_reused")pendingMessageKey="";
  notice("تعذر إرسال الرسالة: "+err.message,"error");
 }finally{loadingButton(form,false)}
});
$("markAllRead").addEventListener("click",async()=>{
 const b=$("markAllRead");b.disabled=true;
 try{
  await request("/api/v1/notifications/read-all",{method:"POST",data:{}});
  await loadUserData();notice("تم تعليم إشعاراتك كمقروءة.","success");
 }catch(err){notice(err.message,"error")}finally{b.disabled=false}
});
$("clientProfile").addEventListener("submit",async e=>{
 e.preventDefault();const form=e.currentTarget;loadingButton(form,true);
 try{
  await request("/api/v1/client/profile",{method:"PATCH",data:{
   company_name:$("clientCompany").value.trim(),city:$("clientCity").value.trim(),
   sector:$("clientSector").value.trim(),bio:$("clientBio").value.trim()
  }});
  notice("تم حفظ ملف العميل في قاعدة البيانات.","success");
 }catch(err){notice(err.message,"error")}finally{loadingButton(form,false)}
});
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

function operationKey(prefix){
 return prefix+"-"+(crypto.randomUUID?.()||Date.now().toString(36)+"-"+Math.random().toString(36).slice(2));
}
const ticketStatus=value=>({
 open:"مفتوحة",in_progress:"قيد المعالجة",resolved:"تم الحل",closed:"مغلقة",
 pending:"بانتظار المراجعة",completed:"مكتملة",rejected:"مرفوضة",
 in_review:"قيد المراجعة",dismissed:"مغلقة بعد المراجعة"
}[value]||String(value||"جديد"));
function safeDate(value){
 if(!value)return "";
 const d=new Date(value);
 return Number.isNaN(d.getTime())?"":d.toLocaleString("ar-SA",{dateStyle:"medium",timeStyle:"short"});
}
async function loadSessions(){
 try{
  const r=await request("/api/v1/account/sessions");
  $("sessionsItems").innerHTML=(r.items||[]).length?r.items.map(item=>{
   const id=Number(item.id),actions=(!item.current&&Number.isSafeInteger(id)&&id>0)
    ?'<button data-action="revoke-session" data-id="'+id+'" type="button">إنهاء هذا الجهاز</button>':"";
   return entry(item.current?"هذا الجهاز · جلسة حالية":(item.device_label||"جهاز مسجل"),
    item.current?"يمكنك إنهاء هذه الجلسة من زر تسجيل الخروج.":"أغلق هذا الجهاز إذا لم تتعرّف عليه.",
    ["آخر نشاط: "+safeDate(item.last_seen_at||item.created_at),
     "انتهاء الجلسة: "+safeDate(item.expires_at)],actions);
  }).join(""):empty("لا توجد جلسات فعالة.");
 }catch(e){$("sessionsItems").innerHTML=empty("تعذر عرض الأجهزة: "+e.message)}
}
async function loadSupport(){
 try{
  const r=await request("/api/v1/support/tickets");
  $("supportItems").innerHTML=(r.items||[]).length?r.items.slice(0,20).map(t=>
   entry("#"+Number(t.id)+" · "+t.subject,t.message||"",
    [ticketStatus(t.status),t.category||"استفسار",safeDate(t.updated_at)],
    t.admin_reply?'<p class="warning">رد الدعم: '+esc(t.admin_reply)+'</p>':"")
  ).join(""):empty("لا توجد تذاكر دعم.");
 }catch(e){$("supportItems").innerHTML=empty("تعذر عرض التذاكر: "+e.message)}
}
async function loadPrivacyRequests(){
 try{
  const r=await request("/api/v1/privacy/requests");
  $("privacyItems").innerHTML=(r.items||[]).length?r.items.slice(0,20).map(x=>
    entry("طلب #"+Number(x.id)+" · "+({
      access:"الاطلاع على البيانات",export:"تصدير",correct:"تصحيح",
      delete:"حذف الحساب",restrict:"تقييد المعالجة"
    }[x.request_type]||x.request_type),x.details||"",
    [ticketStatus(x.status),safeDate(x.created_at)],
    x.admin_note?'<p class="warning">ملاحظة الإدارة: '+esc(x.admin_note)+'</p>':"")
  ).join(""):empty("ما عندك طلبات خصوصية حتى الآن.");
 }catch(e){$("privacyItems").innerHTML=empty("تعذر عرض طلبات الخصوصية: "+e.message)}
}
async function loadSafetyReports(){
 try{
  const r=await request("/api/v1/safety/reports");
  $("safetyItems").innerHTML=(r.items||[]).length?r.items.slice(0,15).map(x=>
   entry("بلاغ #"+Number(x.id)+" · "+(x.category||"مخالفة"),
    x.details||"",[ticketStatus(x.status),safeDate(x.created_at)],"")
  ).join(""):empty("لا توجد بلاغات مرسلة.");
 }catch(e){$("safetyItems").innerHTML=empty("تعذر عرض البلاغات: "+e.message)}
}
async function loadPortfolio(){
 if(currentUser?.role!=="freelancer")return;
 try{
  const r=await request("/api/v1/freelancer/portfolio");
  $("portfolioItems").innerHTML=(r.items||[]).length?r.items.map(x=>
   entry(x.title,x.description||"",[x.external_url||"بدون رابط",safeDate(x.created_at)],
    '<button type="button" data-action="delete-portfolio" data-id="'+Number(x.id)+'">حذف النموذج</button>')
  ).join(""):empty("لا توجد نماذج أعمال. أضف عملًا حقيقيًا لتقوية ملفك المهني.");
 }catch(e){$("portfolioItems").innerHTML=empty("تعذر تحميل معرض أعمالك: "+e.message)}
}
const commercialGateLabels={
 app_environment:"إعداد بيئة تشغيل إنتاجية",
 database_persistence:"استمرارية قاعدة البيانات",
 sms_provider:"مزود رسائل الجوال (اختياري)",
 email_provider:"الإرسال البريدي الحقيقي",
 non_test_email_sender:"عنوان بريد من دومين مملوك",
 verified_email_policy:"تفعيل بريد المستخدم قبل الدخول",
 admin_email_configured:"تعريف مسؤول النظام",
 authentication_provider:"التحقق من الحسابات",
 payment_provider:"تحصيل مدفوعات حقيقي ومؤكد",
 marketplace_payout_settlement:"تسويات وتحويلات المستقلين من مزود مالي معتمد",
 file_storage:"ملفات خاصة مرتبطة بالمنصة",
 kyc_provider:"التحقق الحقيقي من هوية المستقل",
 source_control:"التحديث من مستودع المصدر",
 legal_versions:"توفر نسخ العقود والسياسات",
 legal_review:"اعتماد العقود والسياسات القانونية",
 public_base_url:"رابط HTTPS الرسمي",
 cors_origins:"حماية مصادر الوصول المسموح بها",
 runtime_schema_ensure:"إيقاف تغييرات البنية التلقائية غير المراجعة",
 operational_telemetry:"سجل أحداث التشغيل",
 privacy_account_deletion:"حذف بيانات الحساب والملفات دون بقايا",
 push_provider:"مزود الإشعارات (اختياري)",
 launch_guard:"حاجز الحماية من إطلاق غير معتمد"
};
const commercialMandatoryChecks=[
 "app_environment","authentication_provider","email_provider","verified_email_policy",
 "payment_provider","marketplace_payout_settlement","file_storage",
 "kyc_provider","legal_review","privacy_account_deletion",
 "database_persistence","public_base_url","cors_origins"
];
async function loadLaunchReadiness(){
 if(currentUser?.role!=="admin")return;
 const summary=$("launchReadinessSummary"),items=$("launchReadinessItems");
 summary.textContent="جاري فحص حالة نظام مِنجاز الفعلية.";
 items.innerHTML="";
 try{
  const response=await request("/readiness",{timeoutMs:16000});
  if(!Array.isArray(response.checks))throw Error("استجابة فحص غير مكتملة.");
  const byKey=new Map(response.checks.filter(c=>c&&typeof c.key==="string").map(c=>[c.key,c]));
  const required=response.checks.filter(c=>c.required);
  const allMandatory=commercialMandatoryChecks.every(k=>byKey.has(k)&&byKey.get(k).ok===true);
  const pass=response.ready_for_commercial_launch===true&&allMandatory&&required.every(c=>c.ok===true);
  const failed=required.filter(c=>c.ok!==true);
  const missing=commercialMandatoryChecks.filter(k=>!byKey.has(k));
  if(pass){
   summary.textContent="✅ اجتازت إعدادات الخادم فحص متطلبات الإطلاق. يلزم أيضًا اختبار المعاملات الفعلية والاعتماد القانوني التشغيلي قبل أي إعلان.";
  }else{
   summary.textContent="🔴 الإطلاق التجاري غير معتمد: "+(failed.length+missing.length)+
    " متطلب غير مكتمل أو غير موثق. يُمنع التحصيل وتحويل مستحقات المستقلين حتى استيفائها.";
  }
  items.innerHTML=response.checks.map(c=>entry(
   (c.ok===true?"✅ ":"⛔ ")+(commercialGateLabels[c.key]||c.key),
   c.ok===true?"متحقق وفق الإعدادات الحالية.":"غير متحقق، لا يجوز تجاوزه ببيانات تجريبية.",
   [c.required?"إلزامي":"اختياري",String(c.value??"لم يتم التحقق")],
   ""
  )).join("");
  if(missing.length){
   items.innerHTML+=entry("⛔ متطلبات غير معرّفة في استجابة الخادم",
    "تعذّر التأكد من المتطلبات الأساسية. لا يُقبل الإطلاق.",missing.map(k=>commercialGateLabels[k]||k),"");
  }
  if(response.ready_for_nonfinancial_pilot!==true){
   items.innerHTML+=entry("ملاحظة إطلاق غير مالي",
    "حتى الإطلاق العام دون دفع يحتاج تحقق الهوية والخصوصية والعقود والتخزين. النسخة الحالية ليست تصريح تشغيل تجاري.",[],"");
  }
 }catch(err){
  summary.textContent="⛔ تعذر فحص جاهزية الإطلاق: "+err.message+
   ". حالة الإطلاق غير معتمدة حتى عودة الفحص.";
  items.innerHTML=empty("لا تُفعّل الدفع بناءً على حالة قديمة.");
 }
}

let adminSupportTickets=[],adminCancellations=[],adminSafetyReports=[],adminPrivacyRequests=[];
async function loadAdminQueues(){
 if(currentUser?.role!=="admin")return;
 try{
  const [oper,help,privacy,safety,cancels]=await Promise.all([
   request("/api/admin/operations"),request("/api/admin/support"),
   request("/api/admin/privacy"),request("/api/admin/safety/reports"),
   request("/api/admin/cancellations")
  ]);
  const metrics=oper.metrics||{};
  const pairs=[
   ["حسابات جديدة خلال 24 س",metrics.new_users_24h],
   ["مشاريع مفتوحة",metrics.open_tasks],
   ["طلبات بانتظار الدفع",metrics.awaiting_payment],
   ["بلاغات مفتوحة",metrics.open_safety_reports],
   ["الدعم المفتوح",metrics.open_support],
   ["الخصوصية المعلقة",metrics.pending_privacy],
   ["النزاعات",metrics.open_disputes],
   ["الإلغاءات",metrics.pending_cancellations]
  ];
  $("adminStats").innerHTML=pairs.map(x=>'<article><b>'+Number(x[1]||0)+'</b><small>'+esc(x[0])+'</small></article>').join("");
  adminSupportTickets=help.items||[];
  adminCancellations=cancels.items||[];
  adminSafetyReports=safety.items||[];
  adminPrivacyRequests=privacy.items||[];
  const groups=[
   ["تذاكر الدعم",help.items||[],"subject",["open","in_progress"]],
   ["طلبات الخصوصية",adminPrivacyRequests,"request_type",["pending","in_progress"]],
   ["بلاغات السلامة",adminSafetyReports,"category",["open","in_review"]],
   ["إلغاءات العقود",adminCancellations,"reason",["pending","in_review"]]
  ];
  const counters=groups.map(([name,rows,field,statuses])=>{
    const pending=rows.filter(x=>statuses.includes(x.status));
    return entry(name,"عدد الحالات المفتوحة: "+pending.length,
      pending.slice(0,5).map(x=>("#"+Number(x.id)+" · "+String(x[field]||"حالة"))),"");
  }).join("");
  const urgentSupport=adminSupportTickets.filter(x=>["open","in_progress"].includes(x.status)).slice(0,10).map(x=>
    entry("تذكرة #"+Number(x.id)+" · "+x.subject,x.message||"",
      [ticketStatus(x.status),safeDate(x.updated_at)],
      '<button type="button" data-action="review-support" data-id="'+Number(x.id)+'">الرد على المستخدم</button>')
  ).join("");
  const urgentCancels=adminCancellations.filter(x=>["pending","in_review"].includes(x.status)).slice(0,10).map(x=>
    entry("طلب إلغاء #"+Number(x.id)+" · "+(x.title||"طلب"),x.reason||"",
     [ticketStatus(x.status),x.payment_status==="paid"?"تم الدفع · يلزم إثبات استرداد":"غير مدفوع"],
     '<button type="button" data-action="review-cancel" data-id="'+Number(x.id)+'">مراجعة الطلب</button>')
  ).join("");
  const urgentSafety=adminSafetyReports.filter(x=>["open","in_review"].includes(x.status)).slice(0,12).map(x=>
    entry("بلاغ أمان #"+Number(x.id)+" · "+(x.category||"مخالفة"),x.details||"",
      [ticketStatus(x.status),"المهمة: "+(x.task_title||"-"),"المستخدم المُبلغ عنه: "+(x.reported_user_name||"-")],
      '<button type="button" data-action="review-safety" data-id="'+Number(x.id)+'">مراجعة الأمان</button>')
  ).join("");
  const urgentPrivacy=adminPrivacyRequests.filter(x=>["pending","in_progress"].includes(x.status)).slice(0,12).map(x=>
    entry("طلب خصوصية #"+Number(x.id)+" · "+(x.request_type||"طلب"),x.details||"",
      [ticketStatus(x.status),"مقدم الطلب: "+(x.name||"مستخدم")],
      '<button type="button" data-action="review-privacy" data-id="'+Number(x.id)+'">فرز الطلب</button>')
  ).join("");
  $("adminQueues").innerHTML=counters+urgentSupport+urgentCancels+urgentSafety+urgentPrivacy;
 }catch(e){$("adminQueues").innerHTML=empty("تعذر تحديث بيانات الإدارة: "+e.message)}
}
async function loadExtraPanels(){
 const jobs=[loadSessions(),loadSupport(),loadPrivacyRequests(),loadSafetyReports()];
 if(currentUser?.role==="freelancer")jobs.push(loadPortfolio());
 if(currentUser?.role==="admin")jobs.push(loadAdminQueues(),loadLaunchReadiness());
 await Promise.allSettled(jobs);
}
$("refreshSessions").addEventListener("click",loadSessions);
$("revokeOtherSessions").addEventListener("click",async()=>{
 if(!window.confirm("سيتم تسجيل خروج كل الأجهزة الأخرى من حسابك، لكن جهازك الحالي سيبقى مسجلًا. هل تؤكد؟"))return;
 const b=$("revokeOtherSessions");b.disabled=true;
 try{
  const r=await request("/api/v1/account/sessions/revoke-others",{method:"POST",data:{}});
  await loadSessions();notice("أُغلقت "+Number(r.revoked_count||0)+" جلسة على الأجهزة الأخرى.","success");
 }catch(e){notice(e.message,"error")}finally{b.disabled=false}
});
$("sessionsItems").addEventListener("click",async e=>{
 const b=e.target.closest('button[data-action="revoke-session"]');if(!b)return;
 const id=Number(b.dataset.id);
 if(!Number.isSafeInteger(id)||id<1)return;
 if(!window.confirm("إنهاء جلسة هذا الجهاز؟ سيحتاج صاحبه لتسجيل الدخول مجددًا."))return;
 b.disabled=true;
 try{
  await request("/api/v1/account/sessions/"+id,{method:"DELETE"});
  await loadSessions();notice("تم إنهاء الجلسة المختارة.","success");
 }catch(err){notice(err.message,"error")}finally{b.disabled=false}
});
$("downloadMyData").addEventListener("click",async()=>{
 const b=$("downloadMyData");b.disabled=true;
 try{
  const payload=await request("/api/v1/privacy/export",{timeoutMs:45000});
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json;charset=utf-8"});
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download="minjaz-my-account-"+new Date().toISOString().slice(0,10)+".json";
  document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);
  notice("تم إنشاء ملف بياناتك. احتفظ به في جهاز آمن.","success");
 }catch(e){notice("تعذر تصدير بياناتك: "+e.message,"error")}finally{b.disabled=false}
});
let supportRequestKey="",privacyRequestKey="",portfolioRequestKey="",reportRequestKey="";
$("supportForm").addEventListener("input",()=>{supportRequestKey=""});
$("supportForm").addEventListener("submit",async e=>{
 e.preventDefault();const form=e.currentTarget;loadingButton(form,true);
 const payload={subject:$("supportSubject").value.trim(),
  message:$("supportMessage").value.trim(),category:$("supportCategory").value,
  priority:"normal",idempotency_key:supportRequestKey||(supportRequestKey=operationKey("support"))};
 try{
  const r=await request("/api/v1/support/tickets",{method:"POST",data:payload});
  supportRequestKey="";form.reset();await loadSupport();
  notice("تم فتح تذكرة الدعم رقم "+Number(r.id)+". يمكنك متابعة حالتها في حسابك.","success");
 }catch(err){if(err.code==="idempotency_key_reused")supportRequestKey="";notice(err.message,"error")}
 finally{loadingButton(form,false)}
});
$("privacyForm").addEventListener("input",()=>{privacyRequestKey=""});
$("privacyForm").addEventListener("submit",async e=>{
 e.preventDefault();const form=e.currentTarget;const type=$("privacyType").value;
 if(type==="delete"&&!window.confirm("طلب حذف الحساب سيُرسل للإدارة للمراجعة؛ قد يؤدي حذفه بعد اعتماده إلى فقدان الوصول والبيانات. هل تريد تقديم الطلب؟"))return;
 loadingButton(form,true);
 const payload={request_type:type,details:$("privacyDetails").value.trim(),
  idempotency_key:privacyRequestKey||(privacyRequestKey=operationKey("privacy"))};
 try{
  const r=await request("/api/v1/privacy/requests",{method:"POST",data:payload});
  privacyRequestKey="";form.reset();await loadPrivacyRequests();
  notice("حُفظ طلب الخصوصية رقم "+Number(r.id)+" للمراجعة. لا يُنفّذ الحذف تلقائيًا.","success");
 }catch(err){if(err.code==="idempotency_key_reused")privacyRequestKey="";notice(err.message,"error")}
 finally{loadingButton(form,false)}
});
$("portfolioForm").addEventListener("input",()=>{portfolioRequestKey=""});
$("portfolioForm").addEventListener("submit",async e=>{
 e.preventDefault();if(currentUser?.role!=="freelancer")return;
 const form=e.currentTarget,ext=$("portfolioUrl").value.trim();
 if(ext&&!ext.startsWith("https://")){notice("رابط معرض الأعمال يجب أن يبدأ بـ HTTPS.","error");return}
 loadingButton(form,true);
 const payload={title:$("portfolioTitle").value.trim(),description:$("portfolioDescription").value.trim(),
  external_url:ext,idempotency_key:portfolioRequestKey||(portfolioRequestKey=operationKey("portfolio"))};
 try{
  await request("/api/v1/freelancer/portfolio",{method:"POST",data:payload});
  portfolioRequestKey="";form.reset();await loadPortfolio();
  notice("تمت إضافة نموذج العمل إلى ملفك العام.","success");
 }catch(err){if(err.code==="idempotency_key_reused")portfolioRequestKey="";notice(err.message,"error")}
 finally{loadingButton(form,false)}
});
$("portfolioItems").addEventListener("click",async e=>{
 const b=e.target.closest('button[data-action="delete-portfolio"]');if(!b||currentUser?.role!=="freelancer")return;
 const id=Number(b.dataset.id);
 if(!Number.isSafeInteger(id)||id<1||!window.confirm("هل تريد حذف نموذج العمل من ملفك العام نهائيًا؟"))return;
 b.disabled=true;
 try{
  await request("/api/v1/freelancer/portfolio/"+id,{method:"DELETE"});
  await loadPortfolio();notice("حُذف النموذج من معرض أعمالك.","success");
 }catch(err){notice(err.message,"error")}finally{b.disabled=false}
});
function openReportDialog({task_id=0,order_id=0}={}){
 $("reportTask").value=Number(task_id)||"";
 $("reportOrder").value=Number(order_id)||"";
 $("reportDetails").value="";reportRequestKey="";
 $("reportDialog").showModal();
}
$("closeReport").addEventListener("click",()=>$("reportDialog").close());
$("reportOrderButton").addEventListener("click",()=>{
 if(activeOrderId)openReportDialog({order_id:activeOrderId});
});
$("reportForm").addEventListener("input",()=>{reportRequestKey=""});
$("reportForm").addEventListener("submit",async e=>{
 e.preventDefault();const form=e.currentTarget;loadingButton(form,true);
 const taskId=Number($("reportTask").value),orderId=Number($("reportOrder").value);
 const payload={category:$("reportCategory").value,details:$("reportDetails").value.trim(),
  ...(taskId>0?{task_id:taskId}:{}),...(orderId>0?{order_id:orderId}:{}),
  idempotency_key:reportRequestKey||(reportRequestKey=operationKey("safety"))};
 try{
  const r=await request("/api/v1/safety/reports",{method:"POST",data:payload});
  reportRequestKey="";form.reset();$("reportDialog").close();await loadSafetyReports();
  notice("وصل البلاغ #"+Number(r.id)+" إلى فريق السلامة للمراجعة.","success");
 }catch(err){if(err.code==="idempotency_key_reused")reportRequestKey="";notice(err.message,"error")}
 finally{loadingButton(form,false)}
});
$("adminRefresh").addEventListener("click",loadAdminQueues);
$("refreshLaunchReadiness").addEventListener("click",loadLaunchReadiness);

$("adminQueues").addEventListener("click",e=>{
 const b=e.target.closest('button[data-action="review-safety"]');
 if(!b||currentUser?.role!=="admin")return;
 const id=Number(b.dataset.id),r=adminSafetyReports.find(x=>Number(x.id)===id);
 if(!Number.isSafeInteger(id)||id<1||!r)return;
 $("adminSafetyId").value=String(id);
 $("adminSafetyTitle").textContent="مراجعة بلاغ الأمان #"+id;
 $("adminSafetyDetails").textContent=(r.details||"")+" · مهمة: "+(r.task_title||"-")+" · المستهدف: "+(r.reported_user_name||"-");
 $("adminSafetyStatus").value=r.status==="in_review"?"in_review":"in_review";
 $("adminSafetyNote").value=r.admin_note||"";
 $("adminSafetyTaskAction").value="";
 $("adminSafetyUserAction").value="";
 $("adminSafetyTaskAction").disabled=!Number(r.task_id);
 $("adminSafetyUserAction").disabled=!Number(r.reported_user_id);
 $("adminSafetyDialog").showModal();
});
$("closeAdminSafety").addEventListener("click",()=>$("adminSafetyDialog").close());
$("adminSafetyForm").addEventListener("submit",async e=>{
 e.preventDefault();if(currentUser?.role!=="admin")return;
 const form=e.currentTarget,id=Number($("adminSafetyId").value),report=adminSafetyReports.find(x=>Number(x.id)===id);
 const status=$("adminSafetyStatus").value,task_action=$("adminSafetyTaskAction").disabled?"":$("adminSafetyTaskAction").value,
  user_action=$("adminSafetyUserAction").disabled?"":$("adminSafetyUserAction").value,
  admin_note=$("adminSafetyNote").value.trim();
 if(!report||!Number.isSafeInteger(id)||id<1||!["in_review","resolved","dismissed"].includes(status))return;
 if((task_action||user_action||status!=="in_review")&&admin_note.length<8){
  notice("اكتب سبب القرار والأدلة في 8 أحرف على الأقل.","error");return;
 }
 if((task_action||user_action)&&!window.confirm("هذا الإجراء سيؤثر فورًا على حساب أو مهمة حقيقية. هل راجعت الأدلة وتأكدت من القرار؟"))return;
 if(status==="dismissed"&&(task_action||user_action)){
  notice("لا تجمع إغلاق البلاغ دون إجراء مع تقييد أو إخفاء فعلي.","error");return;
 }
 form.querySelector('button[type="submit"]').disabled=true;
 try{
  const r=await request("/api/admin/safety/reports/"+id,{method:"PATCH",data:{status,task_action,user_action,admin_note}});
  $("adminSafetyDialog").close();await loadAdminQueues();
  notice(r.idempotent_replay?"البلاغ مراجع مسبقًا، لم تتغير حالته.":"تم حفظ قرار الأمان في السجل وإبلاغ الأطراف حسب التغيير.","success");
 }catch(err){notice("تعذرت مراجعة البلاغ: "+err.message,"error")}
 finally{form.querySelector('button[type="submit"]').disabled=false}
});
$("adminQueues").addEventListener("click",e=>{
 const b=e.target.closest('button[data-action="review-privacy"]');
 if(!b||currentUser?.role!=="admin")return;
 const id=Number(b.dataset.id),r=adminPrivacyRequests.find(x=>Number(x.id)===id);
 if(!Number.isSafeInteger(id)||id<1||!r)return;
 $("adminPrivacyId").value=String(id);
 $("adminPrivacyTitle").textContent="فرز طلب الخصوصية #"+id+" · "+(r.request_type||"");
 $("adminPrivacyDetails").textContent=(r.details||"")+" · مقدم الطلب: "+(r.name||"مستخدم");
 $("adminPrivacyStatus").value="in_progress";
 $("adminPrivacyNote").value=r.admin_note||"";
 $("adminPrivacyDialog").showModal();
});
$("closeAdminPrivacy").addEventListener("click",()=>$("adminPrivacyDialog").close());
$("adminPrivacyForm").addEventListener("submit",async e=>{
 e.preventDefault();if(currentUser?.role!=="admin")return;
 const form=e.currentTarget,id=Number($("adminPrivacyId").value),req=adminPrivacyRequests.find(x=>Number(x.id)===id);
 const status=$("adminPrivacyStatus").value,note=$("adminPrivacyNote").value.trim();
 if(!req||!Number.isSafeInteger(id)||id<1||!["in_progress","rejected"].includes(status)||note.length<5)return;
 if(status==="rejected"&&!window.confirm("سيُرفض طلب الخصوصية ويصل إشعار لصاحبه. هل راجعت سبب الرفض والمتطلبات القانونية؟"))return;
 form.querySelector('button[type="submit"]').disabled=true;
 try{
  const r=await request("/api/admin/privacy/"+id,{method:"PATCH",data:{status,admin_note:note}});
  $("adminPrivacyDialog").close();await loadAdminQueues();
  notice(r.idempotent_replay?"حالة الخصوصية لم تتغير.":"تم تسجيل مراجعة طلب الخصوصية وإشعار صاحبه.","success");
 }catch(err){notice("تعذرت مراجعة طلب الخصوصية: "+err.message,"error")}
 finally{form.querySelector('button[type="submit"]').disabled=false}
});


let orderCancelKey="";
$("orderCancelForm").addEventListener("input",()=>{orderCancelKey=""});
$("orderCancelForm").addEventListener("submit",async e=>{
 e.preventDefault();const form=e.currentTarget,id=activeOrderId;
 const reason=$("orderCancelReason").value.trim(),details=$("orderCancelDetails").value.trim();
 if(!id||reason.length<3){notice("اكتب سببًا واضحًا للإلغاء.","error");return}
 if(!window.confirm("طلب الإلغاء يحتاج مراجعة الإدارة، ولن يغيّر حالة الطلب مباشرة. هل تريد إرساله؟"))return;
 loadingButton(form,true);
 const payload={reason,details,idempotency_key:orderCancelKey||(orderCancelKey=operationKey("cancel"))};
 try{
  const r=await request("/api/v1/orders/"+id+"/cancellation",{method:"POST",data:payload});
  orderCancelKey="";form.reset();await showOrder(id,false);
  notice("تم إرسال طلب الإلغاء #"+Number(r.id)+" للإدارة. لم يتغير وضع الدفع.","success");
 }catch(err){if(err.code==="idempotency_key_reused")orderCancelKey="";notice(err.message,"error")}
 finally{loadingButton(form,false)}
});
$("adminQueues").addEventListener("click",e=>{
 const b=e.target.closest('button[data-action="review-cancel"]');
 if(!b||currentUser?.role!=="admin")return;
 const id=Number(b.dataset.id),req=adminCancellations.find(x=>Number(x.id)===id);
 if(!req||!Number.isSafeInteger(id)||id<1)return;
 $("adminCancellationId").value=String(id);
 $("adminCancellationTitle").textContent="مراجعة طلب الإلغاء #"+id;
 $("adminCancellationDetails").textContent=(req.title||"")+" · "+(req.reason||"")+
  (req.payment_status==="paid"?" · تنبيه: تم تحصيل مبلغ ويحتاج إجراء استرداد فعلي.":" · لم يُدفع");
 $("adminCancellationStatus").value="in_review";
 $("adminCancellationNote").value=req.admin_note||"";
 const option=$("adminCancellationStatus").querySelector('option[value="approved"]');
 option.disabled=req.payment_status==="paid";
 $("adminCancellationDialog").showModal();
});
$("closeAdminCancellation").addEventListener("click",()=>$("adminCancellationDialog").close());
$("adminCancellationForm").addEventListener("submit",async e=>{
 e.preventDefault();if(currentUser?.role!=="admin")return;
 const f=e.currentTarget,id=Number($("adminCancellationId").value),
  req=adminCancellations.find(x=>Number(x.id)===id),status=$("adminCancellationStatus").value,
  note=$("adminCancellationNote").value.trim();
 if(!req||!Number.isSafeInteger(id)||id<1||!["in_review","approved","rejected"].includes(status))return;
 if(status==="approved"&&req.payment_status==="paid"){
  notice("لا يمكن اعتماد إلغاء مدفوع هنا دون تسوية واسترداد موثقين.","error");return;
 }
 if(status!=="in_review"&&!window.confirm("قرار الإلغاء سيغيّر حالة الطلب الفعلية ويُبلّغ الأطراف. هل راجعت الأدلة؟"))return;
 loadingButton(f,true);
 try{
  await request("/api/admin/cancellations/"+id,{method:"PATCH",data:{status,admin_note:note}});
  $("adminCancellationDialog").close();await loadAdminQueues();
  notice("حُفظ قرار الإلغاء #"+id+" في سجل الإدارة.","success");
 }catch(err){notice(err.message,"error")}finally{loadingButton(f,false)}
});


$("adminQueues").addEventListener("click",e=>{
 const b=e.target.closest('button[data-action="review-support"]');
 if(!b||currentUser?.role!=="admin")return;
 const id=Number(b.dataset.id);
 const t=adminSupportTickets.find(x=>Number(x.id)===id);
 if(!t||!Number.isSafeInteger(id)||id<1)return;
 $("adminTicketId").value=String(id);
 $("adminTicketTitle").textContent="تذكرة الدعم #"+id+" · "+(t.subject||"");
 $("adminTicketDetails").textContent=t.message||"";
 $("adminTicketStatus").value=t.status==="open"?"in_progress":t.status==="resolved"?"resolved":t.status==="closed"?"closed":"in_progress";
 $("adminTicketReply").value=t.admin_reply||"";
 $("adminTicketDialog").showModal();
});
$("closeAdminTicket").addEventListener("click",()=>$("adminTicketDialog").close());
$("adminTicketForm").addEventListener("submit",async e=>{
 e.preventDefault();if(currentUser?.role!=="admin")return;
 const f=e.currentTarget,id=Number($("adminTicketId").value);
 const status=$("adminTicketStatus").value,reply=$("adminTicketReply").value.trim();
 if(!Number.isSafeInteger(id)||id<1||!["in_progress","resolved","closed"].includes(status)||!reply)return;
 if(["resolved","closed"].includes(status)&&!window.confirm("سيتم تسجيل الحالة وإرسالها في سجل التذكرة. هل تمت معالجة المشكلة فعلًا؟"))return;
 loadingButton(f,true);
 try{
  await request("/api/admin/support/"+id,{method:"PATCH",data:{status,admin_reply:reply}});
  $("adminTicketDialog").close();await loadAdminQueues();
  notice("تم حفظ رد الإدارة وتحديث حالة التذكرة #"+id+".","success");
 }catch(err){notice("تعذر تحديث التذكرة: "+err.message,"error")}finally{loadingButton(f,false)}
});


load();
})();