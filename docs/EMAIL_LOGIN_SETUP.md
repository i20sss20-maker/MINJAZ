# منجاز — إعداد التسجيل بالبريد وتفعيل الحساب (قبل إطلاق الدفع)

هذه الإرشادات تخص فرع `feature/digital-services-geidea-sandbox` على خدمة
`minjaz-digital-services-api` ضمن مشروع Railway `MINJAZ-DIGITAL-SERVICES-TEST`.
**لا تُطبّق إعدادات البيئة التجريبية على الإنتاج مباشرة.**

## الحالة الحالية

- التسجيل الحقيقي يحتاج: الاسم، رقم جوال سعودي، البريد الإلكتروني، كلمة المرور، ونوع الحساب (عميل/مستقل).
- يتلقى المستخدم رابط تفعيل لمرة واحدة لمدة 24 ساعة؛ ولا يمكنه تسجيل الدخول قبل التفعيل.
- تسجيل الدخول يكون بالبريد وكلمة المرور، **بدون رمز OTP في كل مرة**.
- استعادة كلمة المرور تتم برابط بريد لمرة واحدة صالح لـ30 دقيقة، ويُلغي الجلسات السابقة.
- الدخول الإداري يتطلب تطابق بريد الحساب المفعّل مع `ADMIN_EMAIL`.
- إنشاء الطلبات في البيئة التجريبية يُنشئ مسودة فقط **بدون أي دفع حقيقي**.
- حتى 27 أكتوبر 2026، لم تظهر متغيرات `RESEND_API_KEY` و`ADMIN_EMAIL` ضمن إعدادات خدمة Railway التجريبية؛ لهذا لا يمكن اعتماد إرسال التفعيل الفعلي أو دخول المدير حتى تهيئتهما.

## تفعيل إرسال البريد (يجب أن يكون حقيقيًا)

**الخيار المفضل:** Resend API عبر HTTPS، باستخدام نطاق بريد تملكه ووثّقته.
يجب إعداد قيم Railway التالية على خدمة `minjaz-digital-services-api` في **sandbox**:

```text
EMAIL_MODE=resend
EMAIL_FROM=login@your-verified-domain.example
RESEND_API_KEY=<sending-only secret — store in Railway variables>
ADMIN_EMAIL=<exact owner-approved administrator email>
PUBLIC_BASE_URL=https://minjaz-digital-services-api-sandbox.up.railway.app
AUTH_SECRET=<existing strong secret; do not rotate casually>
```

- `EMAIL_FROM` لا بد أن يكون عنوانًا معتمدًا لدى مزود البريد. عنوان `onboarding@resend.dev` للاختبارات المحدودة فقط ولا يضمن إرسالًا عامًا للعملاء.
- إذا استُخدم SMTP بدلًا من Resend، يلزم ضبط `EMAIL_MODE=smtp` و `SMTP_HOST` و `SMTP_PORT` و `SMTP_USERNAME` و `SMTP_PASSWORD` إضافة إلى `EMAIL_FROM`، ويجب التأكد أن خطة الاستضافة تسمح SMTP الصادر.
- لا تضع مفاتيح API أو كلمات مرور SMTP في المحادثة أو GitHub أو رسائل المتصفح.
- لا تُنشئ حساب مدير بالبريد من اختيار المطوّر؛ يعتمد المالك البريد أولًا ثم ينشئ حسابه ويُفعّله.

## الاختبارات المطلوبة قبل نقل أي شيء إلى الإنتاج

1. افحص `GET /api/v1/auth/account-status`، ويجب أن يعرض `configured:true` و`admin_configured:true` بعد إعداد المزود وبريد المدير.
2. سجّل حساب عميل ببريد تختبر وصول الرسائل إليه؛ تأكد أن طلباته مرفوضة قبل التفعيل.
3. افتح رابط التفعيل، ثم سجل الدخول بالبريد وكلمة المرور.
4. أعد إرسال رابط التفعيل وتأكد من إبطال الرابط القديم.
5. اختبر رابط استعادة كلمة المرور، وتأكد من عدم صلاحية الجلسات القديمة بعد التغيير.
6. جرّب حساب مستقل مستقلًا عن العميل.
7. سجّل بحساب البريد المخصص للإدارة واختبر `/digital-services/admin` وإدارة الخدمات والطلبات.
8. اختبر مسار الطلب (مسودة ← تنفيذ ← تسليم ← تعديل ← استلام) بحسابات اختبار **وبدون دفع**.
9. راجع مخرجات GitHub Actions واختبارات PostgreSQL، وراجع إعدادات الأمان والملفات والنسخ الاحتياطية قبل ترقية الفرع.

## روابط التجربة
- المتجر: https://minjaz-digital-services-api-sandbox.up.railway.app/digital-services
- دخول الإدارة: https://minjaz-digital-services-api-sandbox.up.railway.app/digital-services/admin
- فحص الحالة: https://minjaz-digital-services-api-sandbox.up.railway.app/api/v1/auth/account-status

**الدفع آخر مرحلة**: لا تدمج هذه التغييرات في `main` أو تغيّر `PAYMENT_MODE` بسبب نجاح فحوصات الوحدة وحدها.
