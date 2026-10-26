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
<div id="accountStatus" role="status" aria-live="polite" class="account-status"></div>
`;
panel.innerHTML=tpl;
const $=id=>document.getElementById(id);
const sections=["accountSignup","accountLogin","accountRecover","accountNewPassword"];
let resetToken="";
function status(message,isError=false){const el=$("accountStatus");el.textContent=message;el.classList.toggle("error",isError);el.classList.toggle("success",!isError)}
function show(id){for(const section of sections)$(section).hidden=section!==id;$("accountTabSignup").classList.toggle("on",id==="accountSignup");$("accountTabLogin").classList.toggle("on",id==="accountLogin");$("accountTabSignup").setAttribute("aria-selected",String(id==="accountSignup"));$("accountTabLogin").setAttribute("aria-selected",String(id==="accountLogin"));status("")}
async function request(path,body){
 const response=await fetch(path,{method:"POST",credentials:"same-origin",headers:{"Accept":"application/json","Content-Type":"application/json"},body:JSON.stringify(body)});
 let json={};try{json=await response.json()}catch{}
 if(!response.ok){const labels={
  email_not_configured:"خدمة إرسال البريد لم تُجهز بعد. يلزم إعداد بريد الإرسال أولًا.",
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
async function submitForm(event,fn){
 event.preventDefault();const btn=event.currentTarget.querySelector('button[type="submit"]');
 if(btn)btn.disabled=true;
 try{await fn()}catch(err){status(err.message,true)}finally{if(btn)btn.disabled=false}
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
 if(info.registered){$("signupPassword").value="";$("signupConfirm").value="";status("تم إنشاء حسابك. افتح رسالة التفعيل في بريدك، ثم عد لتسجيل الدخول.")}
}));
$("resendActivation").addEventListener("click",async()=>{
 const email=$("signupEmail").value.trim().toLowerCase();if(!email){status("اكتب بريدك في نموذج التسجيل أولًا.",true);return}
 const btn=$("resendActivation");btn.disabled=true;
 try{await request("/api/v1/auth/resend-verification",{email});status("إذا كان الحساب يحتاج تفعيلًا، سيتم إرسال رابط جديد إلى بريده.")}
 catch(err){status(err.message,true)}finally{btn.disabled=false}
});
$("existingAccountForm").addEventListener("submit",e=>submitForm(e,async()=>{
 const email=$("accountEmail").value.trim().toLowerCase(),password=$("accountPassword").value;
 if(!$("accountEmail").checkValidity()||!password){status("أدخل بريدك وكلمة المرور.",true);return}
 await request("/api/v1/auth/login-email",{email,password});
 $("accountPassword").value="";status("تم تسجيل الدخول.");
 if(typeof token!=="undefined"){token="";localStorage.removeItem("minjaz_token")}
 if(typeof boot==="function")await boot();
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
 history.replaceState(null,"",location.pathname+location.search);
 if(match[1]==="reset-password"){
   resetToken=match[2];show("accountNewPassword");status("أدخل كلمة مرور جديدة لإتمام الاستعادة.");return;
 }
 show("accountLogin");status("جارٍ تفعيل بريدك...");
 try{await request("/api/v1/auth/confirm-email",{token:match[2]});status("تم تفعيل بريدك بنجاح. سجّل دخولك الآن بكلمة المرور.")}
 catch(err){status(err.message,true)}
}
consumeActionLink();
fetch("/api/v1/auth/account-status",{credentials:"same-origin"}).then(r=>r.ok?r.json():null).then(x=>{
 if(x&&!x.configured&&!window.location.hash&&$("accountStatus").textContent===""){
   status("التسجيل بالبريد جاهز، لكن إرسال روابط التفعيل يحتاج تهيئة مزود البريد.",true);
 }
}).catch(()=>{});
})();
