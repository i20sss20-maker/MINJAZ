"""Market opportunity relevance and UI filtering; no external network or writes."""
import ast
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
# Extract only the two pure matching functions to avoid importing the live
# server, which deliberately refuses startup without PostgreSQL configuration.
tree=ast.parse((ROOT/"server.py").read_text("utf-8"))
pure=[node for node in tree.body if isinstance(node,ast.FunctionDef)
      and node.name in ("_match_text","opportunity_relevance")]
assert len(pure)==2
namespace={"re":re}
exec(compile(ast.fix_missing_locations(ast.Module(body=pure,type_ignores=[])),
             "server.py:matching-functions","exec"),namespace)
opportunity_relevance=namespace["opportunity_relevance"]

class MatchingAndFiltering(unittest.TestCase):
    def test_unrelated_projects_are_not_marked_matched(self):
        item={"title":"تصميم إعلان مطبوع","description":"تصميم إعلان مطبوع لفريق رياضي",
              "category_name":"التصميم","service_name":"بوستر"}
        score,names=opportunity_relevance(item,["Python","React","PostgreSQL"])
        self.assertEqual(score,0)
        self.assertEqual(names,[])

    def test_category_or_specialization_matches_existing_skills(self):
        item={"title":"تطوير منصة حجز","description":"تطبيق لمواعيد الحجوزات",
              "category_name":"برمجة المواقع","service_name":"مواقع حجوزات"}
        category_score,_=opportunity_relevance(item,["برمجة المواقع"])
        service_score,_=opportunity_relevance(item,["مواقع حجوزات"])
        self.assertGreater(category_score,0)
        self.assertGreater(service_score,0)
        self.assertLessEqual(category_score,95)
        self.assertLessEqual(service_score,95)

    def test_no_skills_does_not_invent_relevance(self):
        item={"title":"واجهة متجر","description":"مطلوب تعديل صفحات متجر",
              "category_name":"برمجة المواقع","service_name":"تطوير الويب"}
        self.assertEqual(opportunity_relevance(item,[]),(0,[]))
        self.assertEqual(opportunity_relevance(item,None),(0,[]))

    def test_role_specific_filters_are_present_and_readable(self):
        page=(ROOT/"public/workspace.html").read_text("utf-8")
        js=(ROOT/"public/workspace-v1.js").read_text("utf-8")
        for select in ("taskMatchFilter","taskSort","taskCategoryFilter","taskServiceFilter"):
            self.assertIn('id="'+select+'"',page)
            self.assertIn('$("'+select+'")',js)
        self.assertIn('id="taskMatchGuide"',page)
        self.assertIn('if(matchChoice!=="all"&&!(Number(t.match_score)>0))return false',js)
        self.assertIn('sortFreelancerTasks()',js)
        self.assertIn('مؤشر ملاءمة:',js)
        self.assertIn('role==="freelancer"',js)

    def test_backend_rejects_mismatched_or_inactive_specializations(self):
        server=(ROOT/"server.py").read_text("utf-8")
        self.assertIn("category_service_mismatch",server)
        self.assertIn("if int(category_id)!=int(svc['category_id'])",server)
        self.assertIn("category_id in (select id from categories where is_active=true)",server)
        self.assertIn("if type(sid) not in (str,int)",server)

if __name__=="__main__":
    unittest.main()
