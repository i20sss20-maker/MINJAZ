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

class PackageCursor(Cursor):
    def execute(self,sql,args=()):
        super().execute(sql,args)
        compact=" ".join(sql.split())
        if "FROM digital_service_packages WHERE id=%s FOR UPDATE" in compact:
            self.row=self.conn.package
        elif "INSERT INTO digital_service_packages" in compact:
            self.row=(91,)
            self.conn.package=(91,)+args
        elif "UPDATE digital_service_packages SET" in compact:
            self.conn.package=(self.conn.package[0],)+args[:8]
        elif "INSERT INTO digital_service_package_events" in compact:
            self.conn.package_events.append(args)
        elif "FROM digital_service_packages ORDER BY id DESC" in compact:
            self.rows=[self.conn.package] if self.conn.package else []
        elif "FROM digital_service_package_events WHERE package_id=%s" in compact:
            self.rows=[("created",None,{"slug":"test-demo"},self.conn.sample_time)]
    def fetchall(self):
        return getattr(self,"rows",[])

class PackageConn(Conn):
    def __init__(self,package=None):
        super().__init__()
        self.package=package
        self.package_events=[]
        from datetime import datetime, timezone
        self.sample_time=datetime.now(timezone.utc)
    def cursor(self):
        return PackageCursor(self)

VALID_PACKAGE={"slug":"test-demo","category":"website","title_ar":"خدمة موقع تجريبية",
               "description_ar":"بناء صفحة تعريفية","price_sar":"100.00",
               "delivery_days":7,"revision_limit":2,"active":False}

class SummaryCursor(Cursor):
    def execute(self,sql,args=()):
        compact=" ".join(sql.split())
        if "GROUP BY status" in compact:
            self.rows=[("draft",2),("delivered",1),("completed",4)]
        elif "COUNT(*)::int FROM digital_service_packages" in compact:
            self.row=(3,)
        elif "COUNT(*)::int FROM digital_service_revisions" in compact:
            self.row=(2,)
        else:
            raise AssertionError("unexpected summary query "+compact)
    def fetchall(self):
        return getattr(self,"rows",[])

class SummaryConn(Conn):
    def cursor(self):
        return SummaryCursor(self)

class WorkflowTests(unittest.TestCase):
    def call(self,path,method,body,actor,db=None):
        if db is None:db=FailConnect()
        return dispatch(method,BASE+path,{},body,actor,(lambda:db) if not isinstance(db,FailConnect) else db)

    def test_package_events_are_admin_only(self):
        self.assertEqual(self.call("admin/packages/91/events","GET",None,None)[0],401)
        self.assertEqual(self.call("admin/packages/91/events","GET",None,CUSTOMER)[0],403)
    def test_admin_reads_package_events(self):
        db=PackageConn()
        code,data=self.call("admin/packages/91/events","GET",None,ADMIN,db)
        self.assertEqual(code,200)
        self.assertEqual(data["events"][0]["action"],"created")
        self.assertEqual(data["events"][0]["after"]["slug"],"test-demo")
        self.assertTrue(db.closed)
    def test_package_events_reject_writes(self):
        self.assertEqual(self.call("admin/packages/91/events","POST",{},ADMIN)[0],405)
    def test_admin_creates_package_with_audit(self):
        db=PackageConn()
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("admin/packages","POST",dict(VALID_PACKAGE),ADMIN,db)
        self.assertEqual(code,201)
        self.assertEqual(data["package_id"],91)
        self.assertEqual(db.commits,1)
        self.assertEqual(len(db.package_events),1)
        self.assertEqual(db.package_events[0][2],"created")
    def test_admin_updates_package_with_audit(self):
        old=(91,"test-demo","website","خدمة موقع تجريبية","بناء صفحة تعريفية",
             "100.00",7,2,False)
        db=PackageConn(old)
        with patch.dict(os.environ,PREVIEW):
            code,data=self.call("admin/packages/91","PATCH",{"active":True},ADMIN,db)
        self.assertEqual(code,200)
        self.assertEqual(data["package"]["active"],True)
        self.assertTrue(db.package[8])
        self.assertEqual(db.package_events[0][2],"updated")
    def test_admin_can_list_packages(self):
        db=PackageConn((91,"test-demo","website","خدمة موقع تجريبية","بناء صفحة تعريفية",
                        "100.00",7,2,False))
        code,data=self.call("admin/packages","GET",None,ADMIN,db)
        self.assertEqual(code,200)
        self.assertEqual(len(data["packages"]),1)
        self.assertEqual(data["packages"][0]["slug"],"test-demo")
    def test_admin_summary_requires_authentication(self):
        self.assertEqual(self.call("admin/summary","GET",None,None)[0],401)
        self.assertEqual(self.call("admin/summary","GET",None,CUSTOMER)[0],403)
    def test_admin_summary_is_read_only_and_aggregates_counts(self):
        db=SummaryConn()
        code,data=self.call("admin/summary","GET",None,ADMIN,db)
        self.assertEqual(code,200)
        self.assertEqual(data["total_orders"],7)
        self.assertEqual(data["active_packages"],3)
        self.assertEqual(data["revisions_last_7_days"],2)
        self.assertEqual(data["by_status"]["completed"],4)
        self.assertEqual(db.commits,0)
        self.assertTrue(db.closed)
    def test_admin_summary_rejects_writes(self):
        self.assertEqual(self.call("admin/summary","POST",{},ADMIN)[0],405)
    def test_package_anonymous_is_denied(self):
        self.assertEqual(self.call("admin/packages","GET",None,None)[0],401)
    def test_package_non_admin_is_denied(self):
        self.assertEqual(self.call("admin/packages","GET",None,CUSTOMER)[0],403)
    def test_package_invalid_category_type_rejected(self):
        data={"slug":"test-demo","category":["ai"],"title_ar":"خدمة تجريبية","description_ar":"",
              "price_sar":"100.00","delivery_days":7,"revision_limit":1,"active":False}
        self.assertEqual(self.call("admin/packages","POST",data,ADMIN)[0],400)
    def test_package_wrong_price_rejected(self):
        data={"slug":"test-demo","category":"ai","title_ar":"خدمة تجريبية","description_ar":"",
              "price_sar":"NaN","delivery_days":7,"revision_limit":1,"active":False}
        self.assertEqual(self.call("admin/packages","POST",data,ADMIN)[0],400)
    def test_package_price_too_precise_rejected(self):
        data={"slug":"test-demo","category":"ai","title_ar":"خدمة تجريبية","description_ar":"",
              "price_sar":"100.001","delivery_days":7,"revision_limit":1,"active":False}
        self.assertEqual(self.call("admin/packages","POST",data,ADMIN)[0],400)
    def test_package_invalid_fields_rejected(self):
        data={"slug":"test-demo","category":"ai","title_ar":"خدمة تجريبية","description_ar":"",
              "price_sar":"100.00","delivery_days":7,"revision_limit":1,"active":False,"is_admin":True}
        self.assertEqual(self.call("admin/packages","POST",data,ADMIN)[0],400)
    def test_package_bad_patch_rejected(self):
        self.assertEqual(self.call("admin/packages/1","PATCH",{"secret":True},ADMIN)[0],400)
    def test_package_create_preview_only(self):
        data={"slug":"test-demo","category":"ai","title_ar":"خدمة تجريبية","description_ar":"",
              "price_sar":"100.00","delivery_days":7,"revision_limit":1,"active":False}
        with patch.dict(os.environ,{"APP_ENV":"production","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,"PAYMENT_MODE":"mock"}):
            self.assertEqual(self.call("admin/packages","POST",data,ADMIN)[0],403)
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
