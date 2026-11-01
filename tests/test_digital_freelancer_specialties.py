"""Unit tests for persistent freelancer specialties and account isolation."""
import unittest

from minjaz_marketplace_specialties import MAX_SPECIALTIES,dispatch,validate_selection

API="/api/v1/freelancer/specialties"
FREELANCER={"id":17,"role":"freelancer"}
CLIENT={"id":20,"role":"client"}

class FakeDb:
    def __init__(self):
        self.users={17,18}
        self.available={101:(2,"تطبيق أندرويد","تطبيقات الجوال"),
                        102:(2,"تطبيق آيفون","تطبيقات الجوال"),
                        103:(5,"تصميم واجهة","تصميم")}
        self.chosen={17:[101],18:[103]}
        self.commits=0;self.rollbacks=0;self.closed=False
    def cursor(self):return FakeCursor(self)
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1
    def close(self):self.closed=True

class FakeCursor:
    def __init__(self,db):self.db=db;self.row=None;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args):
        query=" ".join(sql.split())
        self.rows=[];self.row=None
        if query.startswith("SELECT user_id FROM freelancer_profiles"):
            self.row=(args[0],) if args[0] in self.db.users else None
        elif query.startswith("SELECT s.id FROM services"):
            self.rows=[(x,) for x in args[0] if x in self.db.available]
        elif query.startswith("DELETE FROM freelancer_marketplace_specialties"):
            self.db.chosen[args[0]]=[]
        elif query.startswith("SELECT s.id,s.category_id,s.name_ar,c.name_ar"):
            user=args[0]
            self.rows=[(sid,*self.db.available[sid]) for sid in self.db.chosen.get(user,[])][:args[1]]
        else:raise AssertionError("Unexpected query: "+query)
    def executemany(self,sql,rows):
        assert "INSERT INTO freelancer_marketplace_specialties" in sql
        for user,sid in rows:self.db.chosen.setdefault(user,[]).append(sid)
    def fetchone(self):return self.row
    def fetchall(self):return self.rows

class OwnerScopedSpecialties(unittest.TestCase):
    def test_reject_bad_input_before_touching_db(self):
        for payload in (None,[],{},{"service_ids":"1"},
            {"service_ids":[True]},{"service_ids":[0]},
            {"service_ids":[1,1]},{"service_ids":[2**64]},
            {"service_ids":[1],"user_id":18},
            {"service_ids":list(range(1,MAX_SPECIALTIES+2))}):
            with self.subTest(payload=payload):
                ids,error=validate_selection(payload)
                self.assertIsNone(ids);self.assertTrue(error)

    def test_unauthorized_and_wrong_role_never_open_db(self):
        def denied_db():raise AssertionError("DB access before authentication")
        for actor,status in ((None,401),(CLIENT,403)):
            for method in ("GET","PATCH"):
                self.assertEqual(dispatch(method,API,{"service_ids":[]},actor,denied_db)[0],status)
        self.assertEqual(dispatch("DELETE",API,None,FREELANCER,denied_db)[0],405)
        self.assertEqual(dispatch("GET","/no",None,FREELANCER,denied_db)[0],404)

    def test_owner_can_replace_and_remove_saved_choices(self):
        db=FakeDb()
        def conn():return db
        status,read=dispatch("GET",API,None,FREELANCER,conn)
        self.assertEqual(status,200)
        self.assertEqual([x["service_id"] for x in read["items"]],[101])
        self.assertEqual(db.rollbacks,1)
        status,updated=dispatch("PATCH",API,{"service_ids":[102,103]},FREELANCER,conn)
        self.assertEqual(status,200)
        self.assertEqual([x["service_id"] for x in updated["items"]],[102,103])
        self.assertEqual(db.chosen[18],[103])
        self.assertEqual(db.commits,1)
        status,updated=dispatch("PATCH",API,{"service_ids":[]},FREELANCER,conn)
        self.assertEqual(status,200);self.assertEqual(updated["items"],[])
        self.assertEqual(db.chosen[17],[])
        self.assertEqual(db.chosen[18],[103])

    def test_invalid_or_inactive_choice_cannot_overwrite_saved(self):
        db=FakeDb()
        status,response=dispatch("PATCH",API,{"service_ids":[101,999]},FREELANCER,lambda:db)
        self.assertEqual(status,400)
        self.assertEqual(response["error"],"inactive_or_invalid_specialty")
        self.assertEqual(db.chosen[17],[101])
        self.assertEqual(db.commits,0)

    def test_missing_profile_rejected_without_changes(self):
        db=FakeDb()
        status,_=dispatch("PATCH",API,{"service_ids":[101]},
                          {"id":999,"role":"freelancer"},lambda:db)
        self.assertEqual(status,404)
        self.assertEqual(db.commits,0)

if __name__=="__main__":unittest.main()
