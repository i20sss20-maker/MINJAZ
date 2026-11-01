"""One-time retirement of demo-priced first-party MINJAZ packages.

No production connection. Existing service orders are never deleted.
"""
import unittest
from scripts.curate_minjaz_catalog_preview import DEMO_SLUGS,DEMO_POLICY_VERSION,retire_demos

class Cursor:
    def __init__(self):
        self.active={slug:True for slug in DEMO_SLUGS}
        self.active["custom-owner-service"]=True
        self.marker=None
        self.rowcount=0
        self.row=None
        self.log=[]
    def execute(self,sql,params):
        self.log.append((sql,params))
        if sql.startswith("SELECT disabled_count"):
            self.row=(self.marker,) if self.marker is not None else None
        elif "UPDATE digital_service_packages" in sql:
            assert set(params[0])==set(DEMO_SLUGS)
            self.rowcount=sum(1 for slug in params[0] if self.active[slug])
            for slug in params[0]:self.active[slug]=False
        elif "INSERT INTO minjaz_preview_catalog_policy" in sql:
            assert params[0]==DEMO_POLICY_VERSION
            self.marker=params[1]
        else:raise AssertionError(sql)
    def fetchone(self):return self.row

class HideOldDemoCatalog(unittest.TestCase):
    def test_existing_demos_hidden_without_touching_admin_packages(self):
        self.assertEqual(len(DEMO_SLUGS),3)
        cur=Cursor()
        first=retire_demos(cur)
        self.assertEqual(first,{"applied":True,"retired":3})
        self.assertTrue(cur.active["custom-owner-service"])
        self.assertTrue(all(not cur.active[s] for s in DEMO_SLUGS))
        self.assertEqual(len([q for q,_ in cur.log if "UPDATE " in q]),1)

    def test_repeated_deploy_does_not_rehide_admin_changes(self):
        cur=Cursor()
        retire_demos(cur)
        cur.active[DEMO_SLUGS[0]]=True
        again=retire_demos(cur)
        self.assertEqual(again,{"applied":False,"retired":3})
        self.assertTrue(cur.active[DEMO_SLUGS[0]])
        self.assertEqual(len([q for q,_ in cur.log if "UPDATE " in q]),1)

    def test_already_hidden_record_remains_hidden(self):
        cur=Cursor()
        cur.active[DEMO_SLUGS[0]]=False
        out=retire_demos(cur)
        self.assertEqual(out,{"applied":True,"retired":2})

if __name__=="__main__":unittest.main()
