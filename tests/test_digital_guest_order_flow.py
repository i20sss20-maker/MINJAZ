"""Guest digital-service checkout must require a session before collecting requirements."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

PAGE=(Path(__file__).resolve().parents[1]/"public/digital-services.html").read_text("utf-8")
SCRIPT=PAGE.split("<script>",1)[1].rsplit("</script>",1)[0]

class GuestServiceOrderTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js parser is checked in GitHub CI; unavailable in Python-only release image')
    def test_inline_javascript_parses(self):
        result=subprocess.run(["node","--check"],input=SCRIPT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_service_order_requires_an_active_authenticated_session(self):
        self.assertIn("async function beginServiceOrder(p,card,btn)",SCRIPT)
        begin=SCRIPT.split("async function beginServiceOrder(p,card,btn)",1)[1].split("async function api(",1)[0]
        self.assertIn("await fetch('/api/v1/me'",begin)
        self.assertIn("credentials:'same-origin'",begin)
        self.assertIn("response.status===401",begin)
        self.assertIn("if(!current.user?.id)",begin)
        self.assertLess(begin.index("response.status===401"),begin.index("$('orderDialog').showModal()"))
        self.assertLess(begin.index("if(!current.user?.id)"),begin.index("$('orderDialog').showModal()"))
        self.assertIn("btn.addEventListener('click',()=>beginServiceOrder(p,card,btn))",SCRIPT)

    def test_only_public_package_id_survives_signin(self):
        self.assertIn("PENDING_SERVICE_KEY='minjaz_store_pending_package'",SCRIPT)
        self.assertIn("sessionStorage.setItem(PENDING_SERVICE_KEY,value)",SCRIPT)
        self.assertIn("sessionStorage.removeItem(PENDING_SERVICE_KEY)",SCRIPT)
        self.assertIn("/^[1-9][0-9]{0,10}$/.test(value)",SCRIPT)
        self.assertNotIn("sessionStorage.setItem(PENDING_SERVICE_KEY,requirements)",SCRIPT)
        self.assertNotIn("sessionStorage.setItem(PENDING_SERVICE_KEY,selected)",SCRIPT)

    def test_resume_selected_package_without_auto_submission(self):
        self.assertIn("if(!checkedPendingService)",SCRIPT)
        self.assertIn("const pending=pendingPackageId()",SCRIPT)
        self.assertIn("card.dataset.packageId=String(p.id)",SCRIPT)
        self.assertIn("await beginServiceOrder(packageItem,card,card.querySelector('button'))",SCRIPT)
        self.assertIn("if(needsLogin)hint.append(signInLink())",SCRIPT)
        self.assertIn("a.href='/?auth=login&next=digital-services'",SCRIPT)
        self.assertIn("if(err.code==='unauthorized')$('formError').append(signInLink())",SCRIPT)

    def test_no_real_checkout_or_credential_storage(self):
        self.assertIn("سيُحفظ الطلب كمسودة فقط",PAGE)
        self.assertIn("لا توجد معاملات دفع حقيقية",PAGE)
        helper=SCRIPT.split("// Remember only the chosen public package ID",1)[1].split("async function api(",1)[0]
        self.assertNotIn("password",helper)
        self.assertNotIn("localStorage",helper)

if __name__=="__main__":unittest.main()
