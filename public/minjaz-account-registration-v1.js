/* MINJAZ verified account UI. Registration needs name, phone, email, password.
   Verification and password recovery are one-click email links, not SMS/OTP. */
(function(){
"use strict";
if(typeof DEMO_MODE!=="undefined" && DEMO_MODE)return;
const panel=document.querySelector("#auth .authPanel");
if(!panel)return;
const tpl=`
<div class="brand"><div class="mark">≋</div><span>مِنجاز <small style="font-family:inherit;font-size:12px;color:#8391ad">MINJAZ</small></span></div>
<h1>أنجز أكثر مع منجاز.</h1>
<p>انضم كعميل أو مستقل، وفعّل بريدك الإلكتروني مرة واحدة لحماية حسابك وطلباتك.</p>
<div class="account-tabs" role="tablist" aria-label="اختيار العملية">
 <button id="accountTabSignup" type="button" class="on" role="tab" aria-selected="true">إنشاء حساب</button>
 <button id="accountTabLogin" type="button" role="tab" aria-selected="false">تسجيل الدخول</button>
</div>
<section id="accountSignup" class="account-panel">
 <h2>إنشاء حساب جديد</h2>
 <div class="roleSwitch" aria-label="نوع الحساب">
  <button id="roleClient" type="button" class="on">أنا عميل</button>
  <button id="roleFreelancer" type="button">أنا مستقل</button>
 </div>
 <form id="newAccountForm" novalidate>
  <div class="field"><label for="signupName">الاسم الكامل</label><input id="signupName" autocomplete="name" placeholder="اكتب اسمك" minlength="2" maxlength="120" required></div>
  <div class="field"><label for="signupPhone">رقم الجوال</label><input id="signupPhone" type="tel" inputmode="tel" autocomplete="tel" dir="ltr" placeholder="05xxxxxxxx" required></div>
  <div class="field"><label for="signupEmail">البريد الإلكتروني</label><input id="signupEmail" type="email" inputmode="email" autocomplete="email" dir="ltr" maxlength="254" placeholder="name@example.com" required></div>
  <div class="field"><label for="signupPassword">كلمة المرور (10 أحرف على الأقل)</label><input id="signupPassword" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></div>
  <div class="field"><label for="signupConfirm">تأكيد كلمة المرور</label><input id="signupConfirm" type="password" autocomplete="new-password" minlength="10" required></div>
  <button type="submit" class="btn primary wide">إنشاء حساب وإرسال رابط التفعيل</button>
 </form>
 <p class="account-hint">لا يمكن تسجيل الدخول أو طلب خدمة قبل فتح رابط التفعيل المرسل إلى بريدك.</p>
 <div class="account-resend"><span>لم يصلك رابط التفعيل؟</span><button id="resendActivation" type="button" class="btn soft">إعادة إرسال رابط التفعيل</button></div>
</section>
<section id="accountLogin" class="account-panel" hidden>
 <h2>تسجيل الدخول</h2>
 <form id="existingAccountForm" novalidate>
  <div class="field"><label for="accountEmail">البريد الإلكتروني</label><input id="accountEmail" type="email" autocomplete="email" inputmode="email" dir="ltr" required placeholder="name@example.com"></div>
  <div class="field"><label for="accountPassword">كلمة المرور</label><input id="accountPassword" type="password" autocomplete="current-password" required></div>
  <button type="submit" class="btn primary wide">دخول</button>
 </form>
 <button id="forgotAccountPassword" type="button" class="account-text-button">نسيت كلمة المرور؟</button>
 <p class="account-hint">إذا أنشأت حسابك الآن، فعّله من الرسالة المرسلة إلى بريدك أولًا.</p>
 <button id="resendActivationLogin" type="button" class="account-text-button">لم يصلك رابط التفعيل؟ أعد إرساله</button>
</section>
<section id="accountRecover" class="account-panel" hidden>
 <h2>استعادة كلمة المرور</h2>
 <p>أدخل بريدك الإلكتروني لنرسل لك رابطًا آمنًا لإنشاء كلمة مرور جديدة.</p>
 <form id="accountRecoverForm" novalidate>
  <div class="field"><label for="recoverEmail">البريد الإلكتروني</label><input id="recoverEmail" type="email" autocomplete="email" inputmode="email" dir="ltr" required></div>
  <button class="btn primary wide" type="submit">إرسال رابط إعادة التعيين</button>
 </form>
 <button id="recoverBack" type="button" class="account-text-button">العودة لتسجيل الدخول</button>
</section>
<section id="accountNewPassword" class="account-panel" hidden>
 <h2>تعيين كلمة مرور جديدة</h2>
 <form id="accountResetForm" novalidate>
  <div class="field"><label for="newAccountPassword">كلمة المرور الجديدة</label><input id="newAccountPassword" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></div>
  <div class="field"><label for="newAccountConfirm">تأكيد كلمة المرور</label><input id="newAccountConfirm" type="password" autocomplete="new-password" minlength="10" required></div>
  <button type="submit" class="btn primary wide">حفظ كلمة المرور</button>
 </form>
</section>
<a class="minjaz-service-entry minjaz-service-entry-auth" href="/digital-services">استكشف الخدمات الجاهزة <span aria-hidden="true">↗</span></a>
<p class="account-hint minjaz-service-description">تقدر تتصفح الباقات والأسعار قبل إنشاء الحساب. الطلبات في النسخة التجريبية لا تشمل دفعًا حقيقيًا.</p>
<div id="accountStatus" role="status" aria-live="polite" class="account-status"></div>
`;
panel.innerHTML=tpl;
// The existing MINJAZ marketplace and standalone digital-services catalog now
// share an obvious route for guests and logged-in customers, freelancers and
// administrators. These same-origin anchors do not change account roles,
// authentication state, checkout, or production payment settings.
const storeShortcutStyle=document.createElement("style");
storeShortcutStyle.textContent=`
.minjaz-service-entry{display:inline-flex;align-items:center;justify-content:center;gap:9px;white-space:nowrap;text-decoration:none;background:#eef0ff;border:1px solid #c7cafa;color:#4539aa;border-radius:12px;font-weight:800;font-size:12px;padding:10px 14px;min-height:42px;box-sizing:border-box;transition:background .15s ease,color .15s ease}
.minjaz-service-entry:hover{background:#dedfff;color:#302388}
.minjaz-service-entry:focus-visible{outline:3px solid #887dff;outline-offset:3px}
.minjaz-service-entry-auth{margin-top:18px;width:100%}
.minjaz-service-description{margin:9px 0 2px!important;line-height:1.7!important}
.minjaz-service-entry-app{margin-inline:auto 14px;flex-shrink:0}
@media(max-width:720px){.minjaz-service-entry-app{font-size:10px;padding:8px 10px;min-height:40px;margin-inline:auto 8px;white-space:normal;text-align:center;max-width:118px}}
@media(max-width:430px){.minjaz-service-entry-app{max-width:106px;padding:8px;font-size:10px;line-height:1.35}}
@media(prefers-reduced-motion:reduce){.minjaz-service-entry{transition:none}}
`;
document.head.append(storeShortcutStyle);
const appTopbar=document.querySelector("#app .topbar");
if(appTopbar&&!document.getElementById("minjazServiceEntryApp")){
 const link=document.createElement("a");
 link.id="minjazServiceEntryApp";
 link.className="minjaz-service-entry minjaz-service-entry-app";
 link.href="/digital-services";
 link.textContent="الخدمات الجاهزة";
 link.setAttribute("aria-label","استكشف متجر الخدمات الجاهزة في منجاز");
 const chip=appTopbar.querySelector(".userChip");
 if(chip)appTopbar.insertBefore(link,chip);
 else appTopbar.append(link);
}
const $=id=>document.getElementById(id);
const sections=["accountSignup","accountLogin","accountRecover","accountNewPassword"];
let resetToken="";
const authQuery=new URLSearchParams(window.location.search);
// Only an exact internal destination is supported. Never honor arbitrary redirect URLs.
const STORE_RETURN_KEY="minjaz_store_auth_return";
if(authQuery.get("next")==="digital-services"){
 try{sessionStorage.setItem(STORE_RETURN_KEY,"digital-services")}catch(_){}
}
function returnToStoreAfterLogin(){
 let destination="";
 try{destination=sessionStorage.getItem(STORE_RETURN_KEY)||""}catch(_){}
 if(destination!=="digital-services")return;
 // A successful authentication alone is not enough: boot() must confirm /me.
 if(typeof me==="undefined" || !me || !me.user)return;
 try{sessionStorage.removeItem(STORE_RETURN_KEY)}catch(_){}
 window.location.assign("/digital-services");
}

function status(message,isError=false){const el=$("accountStatus");el.textContent=message;el.classList.toggle("error",isError);el.classList.toggle("success",!isError)}
function show(id){for(const section of sections)$(section).hidden=section!==id;$("accountTabSignup").classList.toggle("on",id==="accountSignup");$("accountTabLogin").classList.toggle("on",id==="accountLogin");$("accountTabSignup").setAttribute("aria-selected",String(id==="accountSignup"));$("accountTabLogin").setAttribute("aria-selected",String(id==="accountLogin"));status("")}
async function request(path,body){
 const response=await fetch(path,{method:"POST",credentials:"same-origin",headers:{"Accept":"application/json","Content-Type":"application/json"},body:JSON.stringify(body)});
 let json={};try{json=await response.json()}catch{}
 if(!response.ok){const labels={
  email_not_configured:"خدمة إرسال البريد لم تُجهز بعد. يلزم إعداد بريد الإرسال أولًا.",
  email_registration_disabled:"التسجيل بالبريد غير مفعّل في هذه البيئة حاليًا.",
  email_delivery_failed:"تعذّر إرسال البريد. جرّب مجددًا أو تحقق من إعدادات بريد الإرسال.",
  invalid_email:"البريد الإلكتروني غير صحيح.",invalid_phone:"اكتب رقم جوال سعودي صحيح.",
  invalid_name:"اكتب اسمًا صحيحًا (حرفان على الأقل).",
  invalid_password:"كلمة المرور يجب أن تكون 10 أحرف على الأقل.",
  invalid_role:"اختر نوع الحساب.",account_already_exists:"البريد أو رقم الجوال مرتبط بحساب موجود. استخدم تسجيل الدخول أو استعادة كلمة المرور.",
  invalid_credentials:"البريد الإلكتروني أو كلمة المرور غير صحيحة.",
  email_not_verified:"فعّل بريدك أولًا من رسالة التفعيل.",
  admin_email_mismatch:"بريد المدير غير معتمد في الإعدادات.",
  invalid_or_used_link:"الرابط غير صحيح أو استُخدم من قبل.",email_link_expired:"انتهت صلاحية الرابط. اطلب رابطًا جديدًا.",
  registration_rate_limited:"تم تجاوز محاولات التسجيل. حاول لاحقًا.",
  login_rate_limited:"محاولات كثيرة. حاول بعد قليل.",
  otp_rate_limited:"الطلبات كثيرة. جرّب لاحقًا.",
  otp_wait:"انتظر دقيقة قبل طلب رابط جديد.",
  sandbox_only:"هذه العملية متاحة على منجاز التجريبي فقط."
 };
 throw new Error(labels[json.error]||json.error||"تعذّر إكمال الطلب. حاول مرة أخرى.");
 }
 return json;
}
let emailCapability=null;
function canSubmitEmailForm(form){
 if(!emailCapability)return true;
 if(!emailCapability.enabled)return false;
 return form.id==="existingAccountForm"||form.id==="accountResetForm"
   ? true : emailCapability.configured===true;
}
async function submitForm(event,fn){
 event.preventDefault();const form=event.currentTarget;
 const btn=form.querySelector('button[type="submit"]');
 if(btn)btn.disabled=true;
 try{await fn()}catch(err){status(err.message,true)}
 finally{if(btn)btn.disabled=!canSubmitEmailForm(form)}
}
$("roleClient").addEventListener("click",()=>{if(typeof setRole==="function")setRole("client")});
$("roleFreelancer").addEventListener("click",()=>{if(typeof setRole==="function")setRole("freelancer")});
$("accountTabSignup").addEventListener("click",()=>show("accountSignup"));
$("accountTabLogin").addEventListener("click",()=>show("accountLogin"));
$("forgotAccountPassword").addEventListener("click",()=>{show("accountRecover");$("recoverEmail").value=$("accountEmail").value});
$("recoverBack").addEventListener("click",()=>show("accountLogin"));
$("newAccountForm").addEventListener("submit",e=>submitForm(e,async()=>{
 const name=$("signupName").value.trim(),phone=$("signupPhone").value.trim(),email=$("signupEmail").value.trim().toLowerCase();
 const password=$("signupPassword").value,confirm=$("signupConfirm").value;
 if(name.length<2||!email||!$("signupEmail").checkValidity()||!phone){status("أكمل الاسم والجوال والبريد الإلكتروني الصحيح.",true);return}
 if(password.length<10){status("اكتب كلمة مرور من 10 أحرف على الأقل.",true);return}
 if(password!==confirm){status("تأكيد كلمة المرور غير مطابق.",true);return}
 const wantedRole=typeof role!=="undefined"&&role==="freelancer"?"freelancer":"client";
 const info=await request("/api/v1/auth/register",{name,phone,email,password,role:wantedRole});
 if(info.registered){
   $("signupPassword").value="";$("signupConfirm").value="";
   $("accountEmail").value=email;$("recoverEmail").value=email;
   show("accountLogin");
   status("تم إنشاء حسابك. افتح رسالة التفعيل في بريدك، وبعدها سجّل الدخول من هنا.");
 }
}));
async function resendActivationFrom(emailInput,buttonId){
 const field=$(emailInput),email=field.value.trim().toLowerCase();
 if(!email||!field.checkValidity()){status("أدخل بريدًا إلكترونيًا صحيحًا لإعادة إرسال رابط التفعيل.",true);return}
 const btn=$(buttonId);btn.disabled=true;
 try{await request("/api/v1/auth/resend-verification",{email});status("إذا كان الحساب يحتاج تفعيلًا، سيتم إرسال رابط جديد إلى بريده.")}
 catch(err){status(err.message,true)}finally{btn.disabled=false}
}
$("resendActivation").addEventListener("click",()=>resendActivationFrom("signupEmail","resendActivation"));
$("resendActivationLogin").addEventListener("click",()=>resendActivationFrom("accountEmail","resendActivationLogin"));
$("existingAccountForm").addEventListener("submit",e=>submitForm(e,async()=>{
 const email=$("accountEmail").value.trim().toLowerCase(),password=$("accountPassword").value;
 if(!$("accountEmail").checkValidity()||!password){status("أدخل بريدك وكلمة المرور.",true);return}
 await request("/api/v1/auth/login-email",{email,password});
 $("accountPassword").value="";status("تم تسجيل الدخول.");
 if(typeof token!=="undefined"){token="";localStorage.removeItem("minjaz_token")}
 if(typeof boot==="function")await boot();
 returnToStoreAfterLogin();
}));
$("accountRecoverForm").addEventListener("submit",e=>submitForm(e,async()=>{
 const email=$("recoverEmail").value.trim().toLowerCase();
 if(!$("recoverEmail").checkValidity()){status("أدخل بريدًا إلكترونيًا صحيحًا.",true);return}
 await request("/api/v1/auth/forgot-password",{email});
 status("إذا كان هذا البريد مرتبطًا بحساب مفعل، سيصلك رابط استعادة كلمة المرور.");
}));
$("accountResetForm").addEventListener("submit",e=>submitForm(e,async()=>{
 const password=$("newAccountPassword").value,confirm=$("newAccountConfirm").value;
 if(!resetToken){status("الرابط غير صحيح. اطلب رابطًا جديدًا.",true);return}
 if(password.length<10||password!==confirm){status("اكتب كلمة مرور من 10 أحرف على الأقل، ثم أكدها.",true);return}
 await request("/api/v1/auth/reset-password",{token:resetToken,password});
 resetToken="";$("newAccountPassword").value="";$("newAccountConfirm").value="";
 show("accountLogin");status("تم تغيير كلمة المرور. سجّل دخولك باستخدام كلمة المرور الجديدة.");
}));
async function consumeActionLink(){
 const hash=window.location.hash.slice(1);
 const match=/^(verify-email|reset-password)=([A-Za-z0-9_-]{35,160})$/.exec(hash);
 if(!match)return;
 document.getElementById("auth")?.classList.remove("hidden");
 document.getElementById("app")?.classList.add("hidden");
 history.replaceState(null,"",location.pathname+location.search);
 if(match[1]==="reset-password"){
   resetToken=match[2];show("accountNewPassword");status("أدخل كلمة مرور جديدة لإتمام الاستعادة.");return;
 }
 show("accountLogin");status("جارٍ تفعيل بريدك...");
 try{await request("/api/v1/auth/confirm-email",{token:match[2]});status("تم تفعيل بريدك بنجاح. سجّل دخولك الآن بكلمة المرور.")}
 catch(err){status(err.message,true)}
}
if(authQuery.get("auth")==="login"&&!window.location.hash)show("accountLogin");
consumeActionLink();
// The UI must not advertise an email-only sign-in path before the API enables it.
// Keep login usable when the sender is temporarily down: verified users do not
// need a new email merely to authenticate.
function applyEmailCapability(info){
 if(!info || typeof info.enabled!=="boolean" || typeof info.configured!=="boolean")return;
 emailCapability=info;
 const enabled=info.enabled===true, senderReady=info.configured===true;
 const signup=$("newAccountForm").querySelector('button[type="submit"]');
 const login=$("existingAccountForm").querySelector('button[type="submit"]');
 const recover=$("accountRecoverForm").querySelector('button[type="submit"]');
 const reset=$("accountResetForm").querySelector('button[type="submit"]');
 signup.disabled=!enabled||!senderReady;
 login.disabled=!enabled;
 recover.disabled=!enabled||!senderReady;
 reset.disabled=!enabled;
 $("resendActivation").disabled=!enabled||!senderReady;
 $("resendActivationLogin").disabled=!enabled||!senderReady;
 $("forgotAccountPassword").disabled=!enabled||!senderReady;
 // Do not overwrite a single-use activation or reset result.
 if(window.location.hash || resetToken || $("accountStatus").textContent)return;
 if(!enabled){
   status("تسجيل الدخول بالبريد غير مفعّل في هذه النسخة. لن يتم إنشاء حساب أو إرسال رسالة تفعيل حتى يكتمل تجهيز النظام.",true);
 }else if(!senderReady){
   status("لم تُربط خدمة البريد بعد. إنشاء الحساب والاستعادة غير متاحين، ويمكن لأصحاب الحسابات المفعّلة تسجيل الدخول.",true);
 }
}
fetch("/api/v1/auth/account-status",{credentials:"same-origin",headers:{"Accept":"application/json"}})
 .then(r=>r.ok?r.json():null).then(applyEmailCapability).catch(()=>{});
})();
