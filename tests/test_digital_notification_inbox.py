"""Notification inbox privacy, read cursor and draft-only safety regression tests."""
import datetime
import unittest
from unittest.mock import patch

from minjaz_digital_services import dispatch
from minjaz_digital_workflow import SANDBOX_PROJECT_ID

NOTICES="/api/digital-services/notifications"
READ=NOTICES+"/read"
ACTOR={"id":11,"role":"customer"}
OTHER={"id":22,"role":"customer"}
NOW=datetime.datetime(2026,10,29,tzinfo=datetime.timezone.utc)
EVENTS=[(3,11,22,"خدمة تطوير","in_progress",NOW,90),
        (4,11,22,"خدمة تطوير","delivered",NOW,90),
        (5,33,22,"خدمة أخرى","in_progress",NOW,91)]

class NoDatabase:
    def __call__(self):
        raise AssertionError("Unexpected DB access")

class FakeConnection:
    def __init__(self):
        self.last_seen={}
        self.events=list(EVENTS)
        self.commits=0
        self.rollbacks=0
        self.closed=False
    def cursor(self):
        return FakeCursor(self)
    def commit(self):
        self.commits+=1
    def rollback(self):
        self.rollbacks+=1
    def close(self):
        self.closed=True

class FakeCursor:
    def __init__(self,db):
        self.db=db
        self.rows=[]
        self.row=None
    def __enter__(self):
        return self
    def __exit__(self,*_args):
        pass
    def execute(self,sql,args):
        normalized=" ".join(sql.split())
        if "SELECT last_seen_event_id" in normalized:
            v=self.db.last_seen.get(args[0])
            self.row=(v,) if v is not None else None
        elif "SELECT ev.id,ev.order_id,p.title_ar" in normalized:
            customer=args[0]
            self.rows=[(id,oid,title,status,created)
                       for id,owner,actor,title,status,created,oid in self.db.events
                       if owner==customer and actor!=customer][:30]
            self.rows.sort(key=lambda row:row[0],reverse=True)
        elif "SELECT COUNT(*) FROM digital_service_order_events" in normalized:
            customer,seen=args
            self.row=(sum(1 for id,owner,actor,*_ in self.db.events
                          if owner==customer and actor!=customer and id>seen),)
        elif "SELECT 1 FROM digital_service_order_events" in normalized:
            target,customer=args
            self.row=(1,) if any(id==target and owner==customer and actor!=customer
                                 for id,owner,actor,*_ in self.db.events) else None
        elif "INSERT INTO digital_service_notification_reads" in normalized:
            customer,target=args
            self.db.last_seen[customer]=max(target,self.db.last_seen.get(customer,0))
            self.row=(self.db.last_seen[customer],)
        else:
            raise AssertionError("Unrecognized query "+normalized)
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows

class NotificationsTests(unittest.TestCase):
    def call(self,method,path,body=None,actor=ACTOR,db=None):
        conn=db or FakeConnection()
        return dispatch(method,path,{},body,actor,lambda:conn)

    def test_anonymous_read_and_write_never_touch_database(self):
        for method,path,body in (("GET",NOTICES,None),
                                  ("POST",READ,{"through_event_id":4})):
            self.assertEqual(dispatch(method,path,{},body,None,NoDatabase())[0],401)
    def test_invalid_cursor_and_method_rejected_without_database(self):
        for value in (None,True,0,-1,3.5,"4",2**63):
            with self.subTest(value=value):
                code,_=dispatch("POST",READ,{},{"through_event_id":value},ACTOR,NoDatabase())
                self.assertEqual(code,400)
        for method,path in (("POST",NOTICES),("GET",READ),("DELETE",READ)):
            self.assertEqual(dispatch(method,path,{},None,ACTOR,NoDatabase())[0],405)
    def test_preview_only_acknowledgement(self):
        with patch.dict("os.environ",{"APP_ENV":"production","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,
                                     "PAYMENT_MODE":"mock"}):
            self.assertEqual(dispatch("POST",READ,{},{"through_event_id":4},ACTOR,NoDatabase())[0],403)
    def test_owner_only_read_and_monotonic_cursor(self):
        db=FakeConnection()
        with patch.dict("os.environ",{"APP_ENV":"preview","RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,
                                     "PAYMENT_MODE":"mock"}):
            code,data=self.call("GET",NOTICES,db=db)
            self.assertEqual(code,200)
            self.assertEqual(data["unread_count"],2)
            self.assertEqual([x["event_id"] for x in data["notifications"]],[4,3])
            self.assertTrue(all(x["unread"] for x in data["notifications"]))
            self.assertEqual(self.call("POST",READ,{"through_event_id":5},db=db)[0],404)
            self.assertEqual(self.call("POST",READ,{"through_event_id":4},actor=OTHER,db=db)[0],404)
            self.assertEqual(db.commits,0)
            self.assertEqual(self.call("POST",READ,{"through_event_id":4},db=db)[0],200)
            self.assertEqual(db.last_seen[11],4)
            code,read=self.call("GET",NOTICES,db=db)
            self.assertEqual(code,200)
            self.assertEqual(read["unread_count"],0)
            self.assertTrue(all(not x["unread"] for x in read["notifications"]))
            # A delayed acknowledgement from another tab must not undo reading.
            self.assertEqual(self.call("POST",READ,{"through_event_id":3},db=db)[0],200)
            self.assertEqual(db.last_seen[11],4)
            db.events.append((6,11,22,"خدمة تطوير","completed",NOW,90))
            self.assertEqual(self.call("GET",NOTICES,db=db)[1]["unread_count"],1)
            self.assertEqual(self.call("GET",NOTICES,actor=OTHER,db=db)[1]["unread_count"],0)
            self.assertEqual(db.commits,2)

if __name__=="__main__":
    unittest.main()
