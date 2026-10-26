"""Draft-order replay, ownership, pricing and validation without external I/O."""
import hashlib
import json
import unittest
from datetime import datetime, timezone
from minjaz_digital_services import dispatch

BASE="/api/digital-services/orders"
KEY="a1b2c3d4-e5f6-4a7b-9c0d-aabbccddee00"
REQ="مطلوب متجر إلكتروني يعرض المنتجات ويتيح التواصل."
BODY={"package_id":7,"requirements":REQ,"idempotency_key":KEY}

def fp(package_id,requirements):
    return hashlib.sha256(json.dumps([package_id,requirements.strip()],
        ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()

class NoDatabase:
    def __call__(self):
        raise AssertionError("invalid input should not access DB")

class Cursor:
    def __init__(self,conn):
        self.db=conn;self.one=None;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=()):
        key=" ".join(sql.split())
        self.db.sql.append((key,args))
        if "SELECT id,request_fingerprint,status FROM digital_service_orders" in key:
            user_id,token=args
            result=self.db.orders.get((user_id,token))
            self.one=(result["id"],result["fingerprint"],result["status"]) if result else None
        elif "SELECT price_sar,revision_limit FROM digital_service_packages" in key:
            self.one=self.db.package if self.db.active and args==(7,) else None
        elif "INSERT INTO digital_service_orders" in key:
            package_id,user_id,requirements,price,limit,token,fingerprint=args
            existing=self.db.orders.get((user_id,token)) if token else None
            if existing:
                self.one=None
            else:
                oid=self.db.seq
                self.db.seq+=1
                record={"id":oid,"fingerprint":fingerprint,"status":"draft",
                        "price":price,"requirements":requirements,"limit":limit}
                self.db.orders[(user_id,token or ("legacy",oid))]=record
                self.one=(oid,)
        elif "SELECT o.id,p.title_ar,o.agreed_price_sar,o.status,o.created_at" in key:
            if "WHERE o.customer_id=%s ORDER BY" in key:
                user_id=args[0]
                self.rows=[(row["id"],"متجر رقمي",row["price"],row["status"],
                            datetime.now(timezone.utc))
                           for (uid,_),row in self.db.orders.items() if uid==user_id]
            elif "WHERE o.id=%s AND o.customer_id=%s" in key:
                order_id,user_id=args
                found=next((v for (uid,_),v in self.db.orders.items()
                            if uid==user_id and v["id"]==order_id),None)
                self.one=(found["id"],"متجر رقمي",found["price"],found["status"],
                    datetime.now(timezone.utc),found["requirements"],None,found["limit"]) if found else None
        elif "SELECT COUNT(*) FROM digital_service_revisions" in key:
            self.one=(0,)
        else:
            raise AssertionError("unexpected SQL: "+key)
    def fetchone(self):return self.one
    def fetchall(self):return self.rows

class Connection:
    def __init__(self):
        self.orders={};self.seq=101;self.package=("3499.00",2)
        self.active=True;self.sql=[];self.autocommit=True
        self.commits=0;self.rollbacks=0;self.closes=0
    def cursor(self):return Cursor(self)
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1
    def close(self):self.closes+=1
    def __call__(self):return self

class OrdersTests(unittest.TestCase):
    def create(self,db,body=BODY,user_id=11):
        return dispatch("POST",BASE,{},body,{"id":user_id},db)
    def test_valid_new_draft(self):
        db=Connection()
        status,data=self.create(db)
        self.assertEqual(status,201)
        self.assertEqual(data,{"order_id":101,"status":"draft","idempotent_replay":False})
        self.assertEqual(db.commits,1)
        self.assertEqual(db.orders[(11,KEY)]["price"],"3499.00")
        self.assertEqual(db.closes,1)
    def test_same_key_and_body_replayed_once(self):
        db=Connection()
        first=self.create(db)
        second=self.create(db)
        self.assertEqual(first[0],201)
        self.assertEqual(second[0],200)
        self.assertEqual(first[1]["order_id"],second[1]["order_id"])
        self.assertTrue(second[1]["idempotent_replay"])
        self.assertEqual(len(db.orders),1)
        self.assertEqual(db.commits,1)
    def test_key_reused_with_different_body_conflicts(self):
        db=Connection()
        self.create(db)
        code,data=self.create(db,{**BODY,"requirements":REQ+" أخرى"})
        self.assertEqual(code,409)
        self.assertEqual(data["error"],"idempotency_key_reused")
        self.assertEqual(len(db.orders),1)
    def test_key_scoped_per_customer(self):
        db=Connection()
        a=self.create(db,user_id=11)
        b=self.create(db,user_id=12)
        self.assertEqual(a[0],201)
        self.assertEqual(b[0],201)
        self.assertNotEqual(a[1]["order_id"],b[1]["order_id"])
    def test_replay_after_package_inactivated(self):
        db=Connection()
        first=self.create(db)
        db.active=False
        second=self.create(db)
        self.assertEqual(second[0],200)
        self.assertEqual(first[1]["order_id"],second[1]["order_id"])
    def test_unavailable_package(self):
        db=Connection();db.active=False
        self.assertEqual(self.create(db)[0],404)
    def test_whitespace_normalization_replays(self):
        db=Connection()
        first=self.create(db)
        second=self.create(db,{**BODY,"requirements":"  "+REQ+"  "})
        self.assertEqual(first[0],201)
        self.assertEqual(second[0],200)
    def test_invalid_token_rejected_without_database(self):
        for bad in (True,1,"short","a"*101,"x"*20+"!",[]):
            with self.subTest(token=bad):
                code,data=dispatch("POST",BASE,{}, {**BODY,"idempotency_key":bad},
                    {"id":11},NoDatabase())
                self.assertEqual(code,400)
                self.assertEqual(data["error"],"invalid_idempotency_key")
    def test_legacy_order_without_key(self):
        db=Connection();body={k:v for k,v in BODY.items() if k!="idempotency_key"}
        a=self.create(db,body)
        b=self.create(db,body)
        self.assertEqual((a[0],b[0]),(201,201))
        self.assertNotEqual(a[1]["order_id"],b[1]["order_id"])
    def test_user_cannot_view_another_users_order(self):
        db=Connection()
        oid=self.create(db,user_id=11)[1]["order_id"]
        code,data=dispatch("GET",BASE+"/"+str(oid),{},None,{"id":12},db)
        self.assertEqual(code,404)
        self.assertEqual(data["error"],"order_not_found")
    def test_owner_reads_order_and_revision_counts(self):
        db=Connection()
        oid=self.create(db)[1]["order_id"]
        code,data=dispatch("GET",BASE+"/"+str(oid),{},None,{"id":11},db)
        self.assertEqual(code,200)
        self.assertEqual(data["order"]["revision_limit"],2)
        self.assertEqual(data["order"]["requirements"],REQ)
        self.assertEqual(data["order"]["revisions_used"],0)
    def test_owner_only_list(self):
        db=Connection()
        self.create(db,user_id=11)
        self.create(db,user_id=12)
        code,data=dispatch("GET",BASE,{},None,{"id":11},db)
        self.assertEqual(code,200)
        self.assertEqual(len(data["orders"]),1)

if __name__=="__main__":unittest.main()
