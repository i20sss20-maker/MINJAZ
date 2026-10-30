"""MINJAZ service curation and marketplace hierarchy regression contracts."""
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.seed_minjaz_full_catalog_preview import CATALOG
from scripts.curate_minjaz_catalog_preview import (
    APPROVED_SLUGS,POLICY_VERSION,SANDBOX_PROJECT_ID,curate,main
)

ROOT=Path(__file__).resolve().parents[1]

class MockCurator:
    def __init__(self):
        self.active={row[0]:True for row in CATALOG}
        self.active["custom-admin-package"]=True
        self.marker=None
        self.rowcount=0
        self.row=None
    def execute(self,sql,args=()):
        if "CREATE TABLE IF NOT EXISTS" in sql:return
        if "SELECT disabled_count" in sql:
            self.row=(self.marker,) if self.marker is not None else None
        elif "UPDATE digital_service_packages" in sql:
            targets=args[0]
            count=0
            for slug in targets:
                if self.active.get(slug,False):
                    self.active[slug]=False
                    count+=1
            self.rowcount=count
        elif "INSERT INTO minjaz_preview_catalog_policy" in sql:
            self.marker=args[1]
        else:
            raise AssertionError("Unknown curation query "+sql)
    def fetchone(self):
        return self.row

class MarketplaceHierarchy(unittest.TestCase):
    def test_curated_list_is_real_subset_without_manual_admin_reset(self):
        self.assertGreaterEqual(len(CATALOG),100)
        self.assertGreaterEqual(len(APPROVED_SLUGS),40)
        self.assertLess(len(APPROVED_SLUGS),len(CATALOG))
        self.assertTrue(APPROVED_SLUGS<={item[0] for item in CATALOG})
        self.assertNotIn("reels-package",APPROVED_SLUGS)
        self.assertNotIn("ads-campaign-setup",APPROVED_SLUGS)
        cur=MockCurator()
        hidden=next(iter(APPROVED_SLUGS))
        cur.active[hidden]=False # Admin intentionally disabled an approved offering.
        first=curate(cur)
        self.assertTrue(first["applied"])
        self.assertEqual(first["disabled"],len(CATALOG)-len(APPROVED_SLUGS))
        self.assertFalse(cur.active[hidden])
        self.assertTrue(cur.active["custom-admin-package"])
        self.assertTrue(all(not cur.active[k] for k in cur.active
                            if k not in APPROVED_SLUGS and k!="custom-admin-package"))
        # The admin is allowed to re-enable an offer after the one-time curation.
        retired=next(row[0] for row in CATALOG if row[0] not in APPROVED_SLUGS)
        cur.active[retired]=True
        again=curate(cur)
        self.assertFalse(again["applied"])
        self.assertTrue(cur.active[retired])

    def test_curation_refuses_unsafe_context(self):
        for variables in (
           {"APP_ENV":"production","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,"MINJAZ_SERVICE_CURATE":"enabled"},
           {"APP_ENV":"preview","RAILWAY_PROJECT_ID":"wrong","MINJAZ_SERVICE_CURATE":"enabled"},
           {"APP_ENV":"preview","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID}):
            with patch.dict(os.environ,variables,clear=True),self.assertRaises(SystemExit):
                main()

    def test_taxonomy_has_all_categories_and_specializations(self):
        sql=(ROOT/"database/migrations/039_marketplace_category_hierarchy.sql").read_text("utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS services",sql)
        self.assertIn("ALTER TABLE services ADD COLUMN IF NOT EXISTS client_guidance",sql)
        self.assertIn("ON CONFLICT (slug) DO NOTHING",sql)
        brief=(ROOT/"database/migrations/040_marketplace_guided_briefs.sql").read_text("utf-8")
        self.assertIn("s.slug LIKE 'market-%'",brief)
        self.assertIn("client_guidance=",brief)
        self.assertIn("freelancer_guidance=",brief)
        self.assertIn("حتى نعرف المطلوب",brief)
        self.assertIn("عند تقديم عرض",brief)
        self.assertGreaterEqual(brief.count("'),"),30)
        parents=set(re.findall(r"\('([a-z_]+)','[^']+','[^']+'\)",sql))
        children=re.findall(r"\('([a-z_]+)','market-([a-z_]+)-([0-9]+)','([^']+)','([^']+)','([^']+)'\)",sql)
        self.assertGreaterEqual(len(parents),30)
        self.assertGreaterEqual(len(children),200)
        slugs=[f"market-{cat}-{number}" for cat,prefix,number,*_ in children]
        self.assertEqual(len(slugs),len(set(slugs)))
        for cat,prefix,num,title,client,freelancer in children:
            with self.subTest(category=cat,number=num):
                self.assertEqual(cat,prefix)
                self.assertIn(cat,parents)
                self.assertGreaterEqual(len(client),30)
                self.assertGreaterEqual(len(freelancer),30)

    def test_real_client_freelancer_and_server_contract(self):
        page=(ROOT/"public/workspace.html").read_text("utf-8")
        js=(ROOT/"public/workspace-v1.js").read_text("utf-8")
        server=(ROOT/"server.py").read_text("utf-8")
        for control in ("categories","taskSubcategories","taskCategoryGuide","insertTaskTemplate",
             "taskCategoryFilter","taskServiceFilter","freelancerSpecialtyCategory",
             "freelancerSpecialty","freelancerSpecialtyGuide","addFreelancerSpecialty"):
            self.assertIn('id="'+control+'"',page)
        self.assertIn('request("/api/v1/categories")',js)
        self.assertIn('request("/api/v1/services")',js)
        self.assertIn('service_id:fd.get("service_id")?',js)
        self.assertIn('updateClientGuidance()',js)
        self.assertIn('updateFreelancerAdvice()',js)
        self.assertIn('t.service_name',js)
        self.assertIn('id="offerSpecialtyGuide"',page)
        for identifier in ("selectedSpecialties","selectedSpecialtiesStatus","saveFreelancerSpecialties"):
            self.assertIn('id="'+identifier+'"',page)
        self.assertIn('request("/api/v1/freelancer/specialties")',js)
        self.assertIn('method:"PATCH",data:{service_ids:selectedSpecialtyIds}',js)
        self.assertIn('specialtiesLoaded=false',js)
        self.assertIn('specialty_match',server)
        self.assertIn("if exact:score=max(score,95)",server)
        self.assertIn("if(matchChoice!==\"all\"&&!(Number(t.match_score)>0))",js)
        self.assertIn('specialty?.freelancer_guidance',js)
        self.assertIn("s.client_guidance,s.freelancer_guidance",server)
        self.assertIn("select id,slug,name_ar,icon from categories where is_active=true",server)
        self.assertIn("left join services s on s.id=t.service_id",server)
        homepage=(ROOT/"public/index.html").read_text("utf-8")
        self.assertIn("marketplace_specialties",server)
        self.assertIn("specialties.map(item=>",homepage)
        self.assertIn("تخصصات المستقل",homepage)
        self.assertIn("وليست شهادة أو إثبات خبرة",homepage)
        self.assertIn("freelancer_marketplace_specialties",server)

if __name__=="__main__":
    unittest.main()
