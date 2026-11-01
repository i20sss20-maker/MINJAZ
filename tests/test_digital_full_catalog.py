"""Contracts for the full MINJAZ sandbox catalog. Never writes real DB data."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import unittest

from scripts.seed_minjaz_full_catalog_preview import CATALOG, seed_catalog, main

ROOT=Path(__file__).resolve().parents[1]
CATEGORIES={"website","mobile_app","ecommerce","branding","maintenance","ai",
            "marketing","seo","content","video","automation","data","security","consulting"}

class Cursor:
    def __init__(self,items=None):
        self.rows=dict(items or {})
        self.queries=[]
        self.last=[]
    def execute(self,sql,args):
        self.queries.append((sql,args))
        if sql.strip().startswith("INSERT"):
            slug=args[0]
            if slug not in self.rows:
                self.rows[slug]={"active":True,"data":args}
        elif sql.strip().startswith("SELECT"):
            self.last=[(slug,self.rows[slug]["active"]) for slug in args[0] if slug in self.rows]
    def fetchall(self):
        return self.last

class FullCatalog(TestCase):
    def test_comprehensive_unique_descriptive_catalog(self):
        self.assertGreaterEqual(len(CATALOG),100)
        self.assertEqual(len({x[0] for x in CATALOG}),len(CATALOG))
        self.assertEqual({x[1] for x in CATALOG},CATEGORIES)
        for slug,category,title,description,price,days,revisions in CATALOG:
            with self.subTest(slug=slug):
                self.assertRegex(slug,r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertIn(category,CATEGORIES)
                self.assertGreaterEqual(len(title.strip()),3)
                self.assertGreaterEqual(len(description.strip()),25)
                self.assertGreater(float(price),0)
                self.assertGreaterEqual(days,1)
                self.assertLessEqual(days,365)
                self.assertLessEqual(revisions,50)

    def test_seed_is_idempotent_and_respects_hidden_admin_catalog(self):
        cursor=Cursor()
        first=seed_catalog(cursor)
        self.assertEqual(first["present"],len(CATALOG))
        self.assertEqual(first["active"],len(CATALOG))
        slug=CATALOG[0][0]
        cursor.rows[slug]={"active":False,"data":("admin-changed",)}
        again=seed_catalog(cursor)
        self.assertEqual(again,{"present":len(CATALOG),"active":len(CATALOG)-1,"hidden":1})
        self.assertEqual(cursor.rows[slug]["data"],("admin-changed",))
        self.assertTrue(all("ON CONFLICT (slug) DO NOTHING" in sql
                          for sql,_ in cursor.queries if sql.strip().startswith("INSERT")))

    def test_seed_refuses_any_environment_without_explicit_sandbox_guard(self):
        for env in (
            {"APP_ENV":"production","MINJAZ_FULL_CATALOG_SEED":"enabled","RAILWAY_PROJECT_ID":"b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4"},
            {"APP_ENV":"preview","MINJAZ_FULL_CATALOG_SEED":"enabled","RAILWAY_PROJECT_ID":"another-project"},
            {"APP_ENV":"preview","RAILWAY_PROJECT_ID":"b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4"},
        ):
            with self.subTest(env=env),patch.dict("os.environ",env,clear=True):
                with self.assertRaises(SystemExit):
                    main()

    def test_api_admin_frontend_and_schema_support_every_category(self):
        api=(ROOT/"minjaz_digital_services.py").read_text("utf-8")
        workflow=(ROOT/"minjaz_digital_workflow.py").read_text("utf-8")
        frontend=(ROOT/"public/digital-services.html").read_text("utf-8")
        admin=(ROOT/"public/digital-services-admin.html").read_text("utf-8")
        migration=(ROOT/"database/migrations/037_digital_services_full_categories.sql").read_text("utf-8")
        docker=(ROOT/"Dockerfile").read_text("utf-8")
        for category in CATEGORIES:
            with self.subTest(category=category):
                self.assertIn("'"+category+"'",api)
                self.assertIn('"'+category+'"',workflow)
                self.assertIn('value="'+category+'"',frontend)
                self.assertIn('value="'+category+'"',admin)
                self.assertIn("'"+category+"'",migration)
        self.assertIn("LIMIT 250",api)
        self.assertIn("catalogVisible+=12",frontend)
        self.assertIn("MINJAZ_FULL_CATALOG_SEED",docker)
        self.assertIn("APP_ENV",docker)
        self.assertIn("python migrate.py &&",docker)
        self.assertIn("سعر",frontend)
        # The public details dialog must be fully read-only until a verified
        # customer explicitly creates a draft. No fabricated order or payment.
        for identifier in ("serviceDetailsDialog","serviceDetailsTitle",
                           "serviceDetailsCategory","serviceDetailsPrice",
                           "serviceDetailsDuration","serviceDetailsRevisions",
                           "serviceDetailsShareLink","serviceDetailsRequest",
                           "serviceDetailsClose","serviceDetailsCopy"):
            self.assertIn('id="'+identifier+'"',frontend)
        self.assertIn("function showServiceDetails(p,card)",frontend)
        self.assertIn("new URL('/digital-services',location.origin)",frontend)
        self.assertIn("if(btn)beginServiceOrder(p,card,btn)",frontend)
        self.assertIn("navigator.clipboard?.writeText",frontend)
        for marker in ("orderPackageSummary","briefGuide","briefQuestions",
                       "selected=p;$('orderTitle')","$('serviceDetailsDialog').showModal()"):
            self.assertIn(marker,frontend)
        for category in CATEGORIES:
            self.assertIn(category+":",frontend)
        self.assertIn("السعر والمدة تُراجع بعد استلام المتطلبات",frontend)
        self.assertIn("المدة تقدير",frontend.replace("المدة التقديرية","المدة تقدير"))
        self.assertNotIn("تم الدفع بنجاح",frontend)
        for control in ("serviceSort","moreServices","categoryFilter","serviceSearch"):
            self.assertIn('id="'+control+'"',frontend)
        for share in ("?service=","encodeURIComponent(p.slug)","catalogDeepLinkChecked","localeCompare"):
            self.assertIn(share,frontend)
        for control in ("packageSearch","packageCategoryFilter","packageVisibilityFilter","moreAdminPackages"):
            self.assertIn('id="'+control+'"',admin)
        self.assertIn("adminPackageVisible+=15",admin)
        for item in ("adminDraftNotice","adminDraftCount","adminViewDrafts"):
            self.assertIn('id="'+item+'"',admin)
        self.assertIn("if(adminAuthenticated&&document.visibilityState==='visible')loadSummary()",admin)
        self.assertIn("$('filter').value='draft';load()",admin)
        for item in ("notifications","notificationsBadge","notificationsRefresh","notificationsMarkRead"):
            self.assertIn('id="'+item+'"',frontend)
        self.assertIn("await api('/api/digital-services/notifications/read'",frontend)
        self.assertIn("through_event_id:lastNotificationEventId",frontend)
        self.assertIn("renderAdminPackages()",admin)
        self.assertIn("ON CONFLICT (slug) DO NOTHING",(ROOT/"scripts/seed_minjaz_full_catalog_preview.py").read_text("utf-8"))

if __name__=="__main__":
    unittest.main()
