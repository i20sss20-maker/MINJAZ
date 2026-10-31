"""Digital-service delivery-link security and visibility tests (no remote DB)."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from minjaz_digital_deliverables import dispatch, _safe_https_url
from minjaz_digital_workflow import SANDBOX_PROJECT_ID

BASE="/api/digital-services/"
ADMIN={"id":8,"role":"admin"}
CUSTOMER={"id":4,"role":"customer"}
OTHER={"id":9,"role":"customer"}
SANDBOX={"APP_ENV":"preview","PAYMENT_MODE":"mock","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID}
FILE={"title":"ملفات التصميم النهائية","url":"https://files.example.com/order-12/design.zip"}

class NoConnection:
    def __call__(self):raise AssertionError("request should be rejected before DB access")

class FakeCursor:
    def __init__(self,db):
        self.db=db;self.one=None;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=()):
        normalized=" ".join(sql.split())
        self.db.queries.append((normalized,args))
        if "SELECT status FROM digital_service_orders" in normalized:
            self.one=(self.db.status,) if self.db.exists else None
        elif "SELECT COUNT(*) FROM digital_service_deliverables" in normalized:
            self.one=(sum(row[0] not in self.db.archived for row in self.db.assets),)
        elif "INSERT INTO digital_service_deliverables" in normalized:
            order,admin_id,title,url=args
            if any(asset[2]==url and asset[0] not in self.db.archived for asset in self.db.assets):
                self.one=None
            else:
                self.db.assets.append((len(self.db.assets)+1,title,url,self.db.now,None))
                self.one=(len(self.db.assets),)
        elif "UPDATE digital_service_deliverables" in normalized and "archived_at=NOW()" in normalized:
            admin_id,asset_id,order_id=args
            found=next((item for item in self.db.assets
                        if item[0]==asset_id and item[4] is None and asset_id not in self.db.archived),None)
            if found:
                self.db.archived.add(asset_id)
                self.db.withdrawn_by[asset_id]=admin_id
                self.one=(asset_id,)
            else:self.one=None
        elif "SELECT 1 FROM digital_service_orders" in normalized:
            if "AND customer_id=%s" in normalized:
                self.one=(1,) if self.db.exists and args[1]==self.db.owner else None
            else:
                self.one=(1,) if self.db.exists else None
        elif "SELECT id,title,url,created_at,published_at" in normalized:
            self.rows=[r for r in self.db.assets if r[0] not in self.db.archived and ("published_at IS NOT NULL" not in normalized or r[4])]
        else:
            raise AssertionError("unexpected SQL: "+normalized)
    def fetchone(self):return self.one
    def fetchall(self):return self.rows

class FakeDB:
    def __init__(self, status="in_progress", owner=4, exists=True, assets=None):
        self.status=status;self.owner=owner;self.exists=exists
        self.now=datetime.now(timezone.utc)
        self.assets=list(assets or [])
        self.archived=set();self.withdrawn_by={}
        self.queries=[];self.commits=0;self.rollbacks=0;self.closed=False
        self.autocommit=True
    def __call__(self):return self
    def cursor(self):return FakeCursor(self)
    def close(self):self.closed=True
    def rollback(self):self.rollbacks+=1
    def commit(self):self.commits+=1

class DeliveryTests(unittest.TestCase):
    def call(self,method,path,actor=None,body=None,db=None):
        return dispatch(method,BASE+path,{},body,actor,db or NoConnection())

    def test_anonymous_cannot_view_links(self):
        self.assertEqual(self.call("GET","orders/12/deliverables")[0],401)
    def test_customer_cannot_use_admin_api(self):
        self.assertEqual(self.call("GET","admin/orders/12/deliverables",CUSTOMER)[0],403)
    def test_customer_cannot_upload_links(self):
        self.assertEqual(self.call("POST","orders/12/deliverables",CUSTOMER,FILE)[0],403)
    def test_invalid_order_id_rejected(self):
        self.assertEqual(self.call("GET","orders/١/deliverables",CUSTOMER)[0],404)
    def test_unsupported_methods_rejected(self):
        self.assertEqual(self.call("DELETE","admin/orders/12/deliverables",ADMIN)[0],405)
    def test_invalid_payload_rejected_before_db(self):
        bad=[None,{"title":"test"},{"url":"https://example.com"},
             {"title":"Hi","url":FILE["url"]},
             {"title":FILE["title"],"url":FILE["url"],"active":True}]
        for item in bad:
            with self.subTest(item=item):
                self.assertEqual(self.call("POST","admin/orders/12/deliverables",ADMIN,item)[0],400)
    def test_public_https_only(self):
        allowed=["https://files.example.com/order.zip",
                 "https://drive.google.com/file/d/sample/view?usp=sharing"]
        rejected=["http://files.example.com/order.zip","javascript:alert(1)",
                  "https://localhost/a","https://user:pass@example.com/a",
                  "https://127.0.0.1/order.zip","https://10.0.0.1/file.zip",
                  "https://internal.local/file.zip","https://example.com:444/file.zip",
                  "https://example.com/a#fragment","https://example.com/a b",
                  "https://example.com/\nfile"]
        self.assertTrue(all(_safe_https_url(x) for x in allowed))
        self.assertTrue(all(not _safe_https_url(x) for x in rejected))
    def test_cannot_add_links_outside_preview(self):
        env={"APP_ENV":"production","PAYMENT_MODE":"mock","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID}
        with patch.dict(os.environ,env):
            self.assertEqual(self.call("POST","admin/orders/12/deliverables",ADMIN,FILE)[0],403)
    def test_cannot_add_links_until_order_started(self):
        db=FakeDB(status="draft")
        with patch.dict(os.environ,SANDBOX):
            code,payload=self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
        self.assertEqual(code,409)
        self.assertEqual(payload["error"],"order_not_in_progress")
        self.assertFalse(db.assets)
    def test_admin_creates_link_as_private_pending_delivery(self):
        db=FakeDB()
        with patch.dict(os.environ,SANDBOX):
            code,payload=self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
        self.assertEqual(code,201)
        self.assertFalse(payload["published"])
        self.assertEqual(db.commits,1)
        self.assertTrue(db.closed)
        self.assertEqual(db.assets[0][4],None)
    def test_duplicate_url_is_rejected(self):
        db=FakeDB()
        with patch.dict(os.environ,SANDBOX):
            self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
        db.closed=False
        with patch.dict(os.environ,SANDBOX):
            code,payload=self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
        self.assertEqual(code,409)
        self.assertEqual(payload["error"],"duplicate_delivery_url")
        self.assertEqual(len(db.assets),1)
    def test_link_limit_is_enforced(self):
        db=FakeDB(assets=[(i,"file "+str(i),"https://example.com/"+str(i),
                            datetime.now(timezone.utc),None) for i in range(25)])
        with patch.dict(os.environ,SANDBOX):
            code,payload=self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
        self.assertEqual(code,409)
        self.assertEqual(payload["error"],"delivery_link_limit_reached")
    def test_customer_only_sees_published_links(self):
        now=datetime.now(timezone.utc)
        db=FakeDB(assets=[(1,"Delivered file","https://example.com/published.zip",now,now),
                          (2,"Pending file","https://example.com/pending.zip",now,None)])
        code,payload=self.call("GET","orders/12/deliverables",CUSTOMER,db=db)
        self.assertEqual(code,200)
        self.assertEqual(len(payload["deliverables"]),1)
        self.assertEqual(payload["deliverables"][0]["title"],"Delivered file")
    def test_other_customer_cannot_see_links(self):
        db=FakeDB()
        self.assertEqual(self.call("GET","orders/12/deliverables",OTHER,db=db)[0],404)
    def test_non_admin_cannot_withdraw_link(self):
        self.assertEqual(self.call("DELETE","admin/orders/12/deliverables/1",CUSTOMER)[0],403)
    def test_cannot_withdraw_published_link(self):
        now=datetime.now(timezone.utc)
        db=FakeDB(assets=[(1,"Public","https://example.com/public.zip",now,now)])
        with patch.dict(os.environ,SANDBOX):
            code,payload=self.call("DELETE","admin/orders/12/deliverables/1",ADMIN,db=db)
        self.assertEqual(code,404)
        self.assertNotIn(1,db.archived)
    def test_unpublished_link_can_be_withdrawn_with_audit(self):
        db=FakeDB()
        with patch.dict(os.environ,SANDBOX):
            self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
            code,data=self.call("DELETE","admin/orders/12/deliverables/1",ADMIN,db=db)
        self.assertEqual(code,200)
        self.assertEqual(data["withdrawn_id"],1)
        self.assertEqual(db.withdrawn_by[1],8)
        code,visible=self.call("GET","admin/orders/12/deliverables",ADMIN,db=db)
        self.assertEqual(code,200)
        self.assertEqual(visible["deliverables"],[])
    def test_withdrawn_url_can_be_readded_as_new_pending_link(self):
        db=FakeDB()
        with patch.dict(os.environ,SANDBOX):
            self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
            self.call("DELETE","admin/orders/12/deliverables/1",ADMIN,db=db)
            code,data=self.call("POST","admin/orders/12/deliverables",ADMIN,FILE,db)
        self.assertEqual(code,201)
        self.assertEqual(data["id"],2)
        self.assertEqual(len(db.assets),2)
    def test_delete_only_allowed_in_working_status(self):
        db=FakeDB(status="delivered")
        with patch.dict(os.environ,SANDBOX):
            code,payload=self.call("DELETE","admin/orders/12/deliverables/1",ADMIN,db=db)
        self.assertEqual(code,409)
        self.assertEqual(payload["error"],"order_not_in_progress")
    def test_delete_requires_sandbox(self):
        env={"APP_ENV":"production","PAYMENT_MODE":"mock","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID}
        with patch.dict(os.environ,env):
            self.assertEqual(self.call("DELETE","admin/orders/12/deliverables/1",ADMIN)[0],403)
    def test_delete_rejects_invalid_asset_id(self):
        self.assertEqual(self.call("DELETE","admin/orders/12/deliverables/١",ADMIN)[0],404)
    def test_admin_can_view_pending_links(self):
        now=datetime.now(timezone.utc)
        db=FakeDB(assets=[(1,"Pending file","https://example.com/pending.zip",now,None)])
        code,payload=self.call("GET","admin/orders/12/deliverables",ADMIN,db=db)
        self.assertEqual(code,200)
        self.assertEqual(len(payload["deliverables"]),1)
        self.assertFalse(payload["deliverables"][0]["published"])

if __name__=="__main__":
    unittest.main()
