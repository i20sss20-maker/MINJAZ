"""Workflow permission, transition and audit tests with no external DB."""
import os
import unittest
from unittest.mock import patch
from minjaz_digital_workflow import dispatch, SANDBOX_PROJECT_ID

BASE = "/api/digital-services/"
ADMIN = {"id":8,"role":"admin"}
CUSTOMER = {"id":4,"role":"customer"}
OTHER = {"id":9,"role":"customer"}
PREVIEW = {"APP_ENV":"preview","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,"PAYMENT_MODE":"mock"}

class FailConnect:
    def __call__(self):
        raise AssertionError("unexpected DB connection")

class Cursor:
    def __init__(self, conn):
        self.conn=conn
        self.row=None
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args):
        sql=" ".join(sql.split())
        self.conn.queries.append((sql,args))
        if "SELECT status,customer_id,agreed_revision_limit" in sql:
            self.row=(self.conn.status,self.conn.customer,self.conn.limit) if self.conn.exists else None
        elif "SELECT COUNT(*) FROM digital_service_revisions" in sql:
            self.row=(self.conn.revisions,)
        elif "INSERT INTO digital_service_revisions" in sql:
            self.conn.revisions+=1
        elif "UPDATE digital_service_orders SET status" in sql:
            self.conn.status=args[0]
        elif "INSERT INTO digital_service_order_events" in sql:
            self.conn.events.append(args)
    def fetchone(self):return self.row

class Conn:
    def __init__(self,status="draft",customer=4,limit=2,revision_count=0,exists=True):
        self.status=status;self.customer=customer;self.limit=limit
        self.revisions=revision_count;self.exists=exists
        self.events=[];self.queries=[];self.commits=0;self.rollbacks=0;self.closed=False
    def cursor(self):return Cursor(self)
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1
    def close(self):self.closed=True

class WorkflowTests(unittest.TestCase):
    def call(self,path,method,body,actor,db=None):
        if db is None:db=FailConnect()
        return dispatch(method,BASE+path,{},body,actor,(lambda:db) if not isinstance(db,FailConnect) else db)

    def test_unauthorized_admin_read(self):
        self.assertEqual(self.call("admin/orders","GET",None,None)[0],401)
    def test_non_admin_read(self):
        self.assertEqual(self.call("admin/orders","GET",None,CUSTOMER)[0],403)
    def test_bad_admin_status_rejected_before_connect(self):
        self.assertEqual(dispatch("GET",BASE+"admin/orders",{"status":["weird"]},None,ADMIN,FailConnect())[0],400)
    def test_admin_invalid_transition_pre_db(self):
        self.assertEqual(self.call("admin/orders/1","PATCH",{"status":"paid"},ADMIN)[0],400)
    def test_admin_delivery_requires_note(self):
        self.assertEqual(self.call("admin/orders/1","PATCH",{"status":"delivered","note":"short"},ADMIN)[0],400)
    def test_invalid_order_id(self):
        self.assertEqual(self.call("admin/orders/١","PATCH",{"status":"in_progress"},ADMIN)[0],404)
    def test_missing_revision_note(self):
        self.assertEqual(self.call("orders/1/revisions","POST",{"note":"no"},CUSTOMER)[0],400)
    def test_sandbox_guard(self):
        with patch.dict(os.environ,{"APP_ENV":"production","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,"PAYMENT_MODE":"mock"}):
            self.assertEqual(self.call("admin/orders/1","PATCH",{"status":"in_progress"},ADMIN)[0],403)
    def test_wrong_project_guard(self):
        with patch.dict(os.environ,{"APP_ENV":"preview","RAILWAY_PROJECT_ID":"wrong","PAYMENT_MODE":"mock"}):
            self.assertEqual(self.call("orders/1/complete","POST",{},CUSTOMER)[0],403)
    def test_admin_can_start_draft_and_audit(self):
        db=Conn()
        with patch.dict(os.environ,PREVIEW):
            result=self.call("admin/orders/11","PATCH",{"status":"in_progress"},ADMIN,db)
        self.assertEqual(result[0],200)
        self.assertEqual(db.status,"in_progress")
        self.assertEqual(db.events[0][1],8)
        self.assertEqual(db.commits,1)
        self.assertTrue(db.closed)
    def test_admin_can_deliver_with_note(self):
        db=Conn(status="in_progress")
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("admin/orders/11","PATCH",{"status":"delivered","note":"العمل مكتمل وجاهز للمراجعة"},ADMIN,db)
        self.assertEqual(code,200)
        self.assertEqual(db.status,"delivered")
        self.assertEqual(len(db.events),1)
    def test_admin_cannot_skip_to_delivery(self):
        db=Conn()
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("admin/orders/11","PATCH",{"status":"delivered","note":"العمل مكتمل وجاهز للمراجعة"},ADMIN,db)
        self.assertEqual(code,409)
        self.assertEqual(db.commits,0)
        self.assertEqual(len(db.events),0)
    def test_ownership_of_revision(self):
        db=Conn(status="delivered")
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("orders/11/revisions","POST",{"note":"يرجى تعديل الواجهة الرئيسية"},OTHER,db)
        self.assertEqual(code,404)
        self.assertEqual(db.revisions,0)
    def test_revision_limit(self):
        db=Conn(status="delivered",limit=1,revision_count=1)
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("orders/11/revisions","POST",{"note":"يرجى تعديل الواجهة الرئيسية"},CUSTOMER,db)
        self.assertEqual(code,409)
        self.assertEqual(db.status,"delivered")
    def test_revision_transition_and_audit(self):
        db=Conn(status="delivered",limit=2)
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("orders/11/revisions","POST",{"note":"يرجى تعديل الواجهة الرئيسية"},CUSTOMER,db)
        self.assertEqual(code,200)
        self.assertEqual(db.revisions,1)
        self.assertEqual(db.status,"revision_requested")
        self.assertEqual(len(db.events),1)
    def test_customer_completes_delivered(self):
        db=Conn(status="delivered")
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("orders/11/complete","POST",{},CUSTOMER,db)
        self.assertEqual(code,200)
        self.assertEqual(db.status,"completed")
        self.assertEqual(db.commits,1)
    def test_customer_cannot_complete_draft(self):
        db=Conn()
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("orders/11/complete","POST",{},CUSTOMER,db)
        self.assertEqual(code,409)
    def test_customer_can_cancel_draft(self):
        db=Conn()
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("orders/11/cancel","POST",{},CUSTOMER,db)
        self.assertEqual(code,200)
        self.assertEqual(db.status,"cancelled")

if __name__=="__main__":
    unittest.main()
