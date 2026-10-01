CREATE TABLE IF NOT EXISTS users(
  id BIGSERIAL PRIMARY KEY,
  phone TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL DEFAULT 'مستخدم',
  role TEXT NOT NULL CHECK(role IN ('client','freelancer','admin')),
  is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles(
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('client','freelancer','admin')),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(user_id,role)
);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role,user_id);
INSERT INTO user_roles(user_id,role,enabled) SELECT id,role,TRUE FROM users ON CONFLICT(user_id,role) DO UPDATE SET enabled=TRUE;

CREATE TABLE IF NOT EXISTS sessions(
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
CREATE TABLE IF NOT EXISTS otp_challenges(
  id BIGSERIAL PRIMARY KEY,
  challenge_id UUID UNIQUE NOT NULL,
  phone TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT 'login',
  attempts INT NOT NULL DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS categories(
  id BIGSERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name_ar TEXT NOT NULL,
  icon TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS freelancer_profiles(
  user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  bio TEXT,
  skills TEXT[] NOT NULL DEFAULT '{}',
  rating NUMERIC(3,2) NOT NULL DEFAULT 0,
  completed_tasks INT NOT NULL DEFAULT 0,
  on_time_rate NUMERIC(5,2) NOT NULL DEFAULT 100,
  avg_response_minutes INT,
  is_available BOOLEAN NOT NULL DEFAULT FALSE,
  kyc_status TEXT NOT NULL DEFAULT 'pending' CHECK(kyc_status IN ('pending','approved','rejected'))
);

INSERT INTO user_roles(user_id,role,enabled) SELECT user_id,'freelancer',TRUE FROM freelancer_profiles ON CONFLICT(user_id,role) DO UPDATE SET enabled=TRUE;
CREATE TABLE IF NOT EXISTS tasks(
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES users(id),
  category_id BIGINT REFERENCES categories(id),
  service_id BIGINT,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  budget_min NUMERIC(10,2),
  budget_max NUMERIC(10,2),
  urgency TEXT NOT NULL DEFAULT 'normal' CHECK(urgency IN ('normal','urgent')),
  due_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('draft','open','matched','in_progress','delivered','completed','cancelled','disputed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_client ON tasks(client_id,created_at DESC);
CREATE TABLE IF NOT EXISTS proposals(
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  freelancer_id BIGINT NOT NULL REFERENCES users(id),
  price NUMERIC(10,2) NOT NULL,
  delivery_hours INT NOT NULL DEFAULT 24,
  revisions INT NOT NULL DEFAULT 1,
  message TEXT,
  status TEXT NOT NULL DEFAULT 'sent' CHECK(status IN ('sent','accepted','rejected','withdrawn')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(task_id,freelancer_id)
);
CREATE TABLE IF NOT EXISTS orders(
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT UNIQUE NOT NULL REFERENCES tasks(id),
  proposal_id BIGINT REFERENCES proposals(id),
  client_id BIGINT NOT NULL REFERENCES users(id),
  freelancer_id BIGINT NOT NULL REFERENCES users(id),
  amount NUMERIC(10,2) NOT NULL,
  platform_fee NUMERIC(10,2) NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'awaiting_payment' CHECK(status IN ('awaiting_payment','in_progress','delivered','revision_requested','completed','cancelled','disputed')),
  payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK(payment_status IN ('unpaid','paid','refunded','partially_refunded')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS messages(
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  sender_id BIGINT NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS deliveries(
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  freelancer_id BIGINT NOT NULL REFERENCES users(id),
  note TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reviews(
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  reviewer_id BIGINT NOT NULL REFERENCES users(id),
  reviewee_id BIGINT NOT NULL REFERENCES users(id),
  quality INT NOT NULL CHECK(quality BETWEEN 1 AND 5),
  timeliness INT NOT NULL CHECK(timeliness BETWEEN 1 AND 5),
  communication INT NOT NULL CHECK(communication BETWEEN 1 AND 5),
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS favorite_freelancers(
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  freelancer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(client_id,freelancer_id)
);
CREATE TABLE IF NOT EXISTS support_tickets(
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT 'general',
  subject TEXT NOT NULL,
  message TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'normal',
  status TEXT NOT NULL DEFAULT 'open',
  admin_reply TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS privacy_requests(
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  request_type TEXT NOT NULL CHECK(request_type IN ('access','export','correct','delete','restrict')),
  details TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  admin_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
INSERT INTO categories(slug,name_ar,icon) VALUES
('design','تصميم','🎨'),
('writing','كتابة ومحتوى','✍️'),
('excel','Excel وبيانات','📊'),
('files','Word وPDF','📄'),
('video','فيديو وصوت','🎬'),
('translation','ترجمة','🌐'),
('business','أعمال','💼'),
('ai','ذكاء اصطناعي','✨')
ON CONFLICT(slug) DO NOTHING;


CREATE TABLE IF NOT EXISTS order_disputes (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  opened_by BIGINT NOT NULL REFERENCES users(id),
  reason TEXT NOT NULL,
  details TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  previous_order_status TEXT,
  previous_task_status TEXT,
  resolution_action TEXT,
  resolution_note TEXT,
  resolved_by BIGINT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_order_disputes_order ON order_disputes(order_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_disputes_status ON order_disputes(status,created_at DESC);

CREATE TABLE IF NOT EXISTS attachments(
  id BIGSERIAL PRIMARY KEY,
  uploaded_by BIGINT NOT NULL REFERENCES users(id),
  task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
  order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
  message_id BIGINT REFERENCES messages(id) ON DELETE CASCADE,
  delivery_id BIGINT REFERENCES deliveries(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  file_url TEXT NOT NULL,
  mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  size_bytes BIGINT NOT NULL DEFAULT 0,
  storage_mode TEXT NOT NULL DEFAULT 'external_link',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK(task_id IS NOT NULL OR order_id IS NOT NULL OR message_id IS NOT NULL OR delivery_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_attachments_task ON attachments(task_id,created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_order ON attachments(order_id,created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id,created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_delivery ON attachments(delivery_id,created_at);

CREATE TABLE IF NOT EXISTS order_revision_requests(
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  requested_by BIGINT NOT NULL REFERENCES users(id),
  sequence_no INT NOT NULL,
  note TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  satisfied_at TIMESTAMPTZ,
  UNIQUE(order_id,sequence_no)
);
CREATE INDEX IF NOT EXISTS idx_revision_requests_order ON order_revision_requests(order_id,created_at);


CREATE TABLE IF NOT EXISTS order_events(
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  actor_id BIGINT REFERENCES users(id),
  event_type TEXT NOT NULL,
  title TEXT NOT NULL,
  details TEXT,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events(order_id,created_at);


CREATE TABLE IF NOT EXISTS user_notifications_v2(
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'general',
  title TEXT NOT NULL,
  body TEXT,
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_notifications_v2_user ON user_notifications_v2(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_v2_unread ON user_notifications_v2(user_id,read_at,created_at DESC);

CREATE TABLE IF NOT EXISTS services(
  id BIGSERIAL PRIMARY KEY,
  category_id BIGINT NOT NULL REFERENCES categories(id),
  slug TEXT UNIQUE NOT NULL,
  name_ar TEXT NOT NULL,
  description_ar TEXT,
  min_price NUMERIC(10,2),
  max_price NUMERIC(10,2),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_services_category ON services(category_id,active,id);
INSERT INTO services(category_id,slug,name_ar,description_ar,min_price,max_price)
SELECT c.id,v.slug,v.name_ar,v.description_ar,v.min_price,v.max_price
FROM (VALUES
('design','social-post-1','تصميم منشور سوشال واحد','تصميم منشور جاهز للنشر بالمقاس المطلوب',49,79),
('design','social-posts-3','تصميم 3 منشورات سوشال','ثلاثة تصاميم متناسقة لهوية الحساب',79,149),
('design','banner-ad','تصميم بانر أو إعلان','بانر رقمي أو إعلان بمقاس واحد',49,99),
('design','menu-price-list','تصميم منيو أو قائمة أسعار','تنسيق بصري احترافي لقائمة خدمات أو أسعار',99,249),
('design','business-card','تصميم بطاقة عمل','بطاقة عمل بوجه أو وجهين',49,99),
('design','simple-logo','تصميم شعار بسيط','شعار بسيط لمشروع صغير مع ملف نهائي',99,299),
('design','invitation-certificate','دعوة أو شهادة أو بطاقة','تصميم بطاقة مناسبة أو شهادة أو دعوة',49,99),
('design','resize-designs','تعديل مقاسات تصاميم','إعادة تجهيز التصاميم لمقاسات منصات مختلفة',49,99),
('files','ppt-10','عرض PowerPoint حتى 10 شرائح','تنسيق عرض واضح ومرتب حتى 10 شرائح',79,149),
('files','ppt-20','عرض PowerPoint حتى 20 شريحة','تنسيق عرض احترافي حتى 20 شريحة',149,299),
('files','word-format-20','تنسيق Word حتى 20 صفحة','تنسيق العناوين والجداول والهوامش والفهرسة البسيطة',49,99),
('files','pdf-tools','دمج أو ترتيب أو تحويل PDF','دمج وترتيب وتحويل ملفات PDF',49,79),
('files','word-pdf-form','إنشاء نموذج Word أو PDF','إنشاء نموذج منظم قابل للتعبئة أو الطباعة',49,99),
('design','cv-design','تصميم سيرة ذاتية','تنسيق سيرة ذاتية حديثة وواضحة',79,149),
('design','company-profile','بروفايل شركة صغير','تصميم ملف تعريفي مختصر لشركة أو مشروع',149,299),
('excel','excel-clean','تنظيف وتنسيق Excel','تنظيف الجدول وتوحيد التنسيق والقيم',49,99),
('excel','excel-formulas','معادلات Excel','إضافة أو إصلاح معادلات وصيغ Excel',79,149),
('excel','excel-charts','رسوم وتقرير Excel','إنشاء رسوم بيانية وتقرير مختصر من البيانات',79,149),
('excel','excel-dashboard','Dashboard Excel بسيط','لوحة مؤشرات بسيطة ومترابطة داخل Excel',149,299),
('excel','data-entry-300','إدخال بيانات حتى 300 صف','إدخال وتنظيم بيانات حتى 300 صف',49,99),
('excel','merge-dedupe','دمج وإزالة تكرار البيانات','دمج ملفات أو جداول وإزالة السجلات المكررة',49,99),
('excel','google-sheet','تنظيم Google Sheet','إعداد جدول منظم وسهل الاستخدام',79,149),
('writing','product-desc-10','كتابة 10 أوصاف منتجات','أوصاف منتجات مختصرة وواضحة للبيع الإلكتروني',59,119),
('writing','social-copy-10','كتابة 10 منشورات سوشال','نصوص جاهزة للنشر لوسائل التواصل',79,149),
('writing','proofread-1500','تدقيق 1500 كلمة','تدقيق لغوي وإملائي حتى 1500 كلمة',49,79),
('writing','rewrite-1500','إعادة صياغة 1500 كلمة','إعادة صياغة تحافظ على المعنى وتحسن الأسلوب',49,99),
('translation','translate-1000','ترجمة حتى 1000 كلمة','ترجمة نص حتى 1000 كلمة بين اللغات المدعومة',59,129),
('writing','transcribe-30','تفريغ صوت حتى 30 دقيقة','تحويل تسجيل صوتي إلى نص منظم',59,129),
('writing','summarize-30','تلخيص حتى 30 صفحة','تلخيص محتوى طويل إلى نقاط وأفكار أساسية',59,129),
('business','research-sources','جمع مصادر ومعلومات','جمع معلومات عامة ومصادر مرتبة حول موضوع محدد',59,149),
('design','remove-bg-20','إزالة خلفية حتى 20 صورة','قص وإزالة الخلفيات وتسليم PNG',49,79),
('design','retouch-5','تحسين 5 صور','تحسين إضاءة وألوان وتنظيف بسيط لخمس صور',59,119),
('design','product-images-3','تجهيز 3 صور منتجات','تهيئة صور منتجات نظيفة ومتناسقة للمتجر',59,129),
('video','reel-under-1','مونتاج Reel أقل من دقيقة','مونتاج فيديو قصير مع قص وانتقالات بسيطة',79,149),
('video','subtitles-5','إضافة ترجمة لفيديو حتى 5 دقائق','إضافة نصوص أو ترجمة زمنية لفيديو قصير',59,119),
('video','video-1-3','مونتاج فيديو 1–3 دقائق','مونتاج فيديو متوسط مع ترتيب المقاطع والصوت',119,299),
('video','audio-clean-15','تنظيف صوت حتى 15 دقيقة','تقليل ضوضاء وتحسين مستوى الصوت',59,129),
('design','thumbnail-cover','تصميم صورة مصغرة أو غلاف','غلاف أو Thumbnail جذاب بمقاس واحد',49,79),
('business','upload-products-20','رفع 20 منتج','إدخال بيانات وصور 20 منتج في متجر إلكتروني',79,149),
('excel','product-file-50','تجهيز ملف 50 منتج','تنظيم بيانات حتى 50 منتج في ملف جاهز',79,149),
('design','quotation-design','تصميم قائمة أسعار أو عرض سعر','تصميم عرض سعر أو قائمة أسعار مرتبة',59,119),
('business','content-plan-2w','خطة محتوى لأسبوعين','خطة نشر وأفكار محتوى لمدة أسبوعين',99,199),
('business','competitors-5','مقارنة 5 منافسين','مقارنة عامة ومنظمة لخمس جهات منافسة',99,199),
('business','businesses-30','جمع بيانات 30 نشاطًا','جمع معلومات عامة متاحة لثلاثين نشاطًا تجاريًا',79,149),
('writing','meeting-summary','تلخيص اجتماع أو تسجيل','تلخيص القرارات والنقاط المهمة من اجتماع أو تسجيل',59,129),
('writing','cs-replies-15','صياغة 15 رد خدمة عملاء','ردود جاهزة ومهنية لسيناريوهات خدمة العملاء',59,129),
('ai','ai-prompts','إعداد Prompts أو Workflow بالذكاء الاصطناعي','صياغة تعليمات وقوالب استخدام عملية للذكاء الاصطناعي',79,149),
('ai','ai-classify-data','تصنيف بيانات غير حساسة بالذكاء الاصطناعي','تنظيم وتصنيف بيانات غير حساسة وفق قواعد واضحة',79,199),
('ai','no-code-automation','أتمتة No-code بسيطة','إعداد أتمتة بسيطة بين أدوات مدعومة',149,299),
('business','cms-edits','تعديلات محتوى CMS بسيطة','تحديث نصوص وصور ومحتوى بسيط داخل نظام إدارة محتوى',79,199)
) AS v(category_slug,slug,name_ar,description_ar,min_price,max_price)
JOIN categories c ON c.slug=v.category_slug
ON CONFLICT(slug) DO UPDATE SET category_id=EXCLUDED.category_id,name_ar=EXCLUDED.name_ar,description_ar=EXCLUDED.description_ar,min_price=EXCLUDED.min_price,max_price=EXCLUDED.max_price,active=TRUE;

CREATE TABLE IF NOT EXISTS payout_requests(
  id BIGSERIAL PRIMARY KEY,
  freelancer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount NUMERIC(10,2) NOT NULL CHECK(amount>0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','paid','rejected','cancelled')),
  note TEXT,
  admin_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_payout_requests_freelancer ON payout_requests(freelancer_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payout_requests_status ON payout_requests(status,created_at DESC);