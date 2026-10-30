"""Privacy object deletion: never finalize a request while private S3 bytes remain."""
import inspect
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from minjaz_privacy_storage import (
    normalize_object_keys,enqueue_deletions,drain_pending,start_preview_worker)

ROOT=Path(__file__).resolve().parents[1]
KEY="uploads/17/2026/10/"+"a"*32+".pdf"

class FakeStorage:
    ready=True
    def __init__(self,action="success"):self.action=action;self.calls=[]
    def safe_key_for_user(self,key,uid):
        import re
        return bool(re.fullmatch(r'uploads/'+str(uid)+r'/\d{4}/\d{2}/[a-f0-9]{32}\.pdf',key))
    def delete(self,key,timeout=10):
        self.calls.append(key)
        return self.action=="success"
    def head(self,key,timeout=8):
        if self.action=="already_deleted":
            raise urllib.error.HTTPError("https://private.invalid",404,"Gone",{},None)
        return {"size_bytes":45}

class FakeDb:
    def __init__(self,rows):
        self.rows=rows;self.status="in_progress";self.commits=0;self.rollbacks=0;self.closed=False
    def cursor(self,**kwargs):return FakeCursor(self)
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1
    def close(self):self.closed=True

class FakeCursor:
    def __init__(self,db):self.db=db;self.selected=None;self.new=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args=None):
        sql=" ".join(sql.split())
        if sql.startswith("SELECT id,user_id,privacy_request_id,object_key"):
            matches=[x for x in self.db.rows if not x.get("deleted") and not x.get("attempted")]
            self.selected=dict(matches[0]) if matches else None
        elif sql.startswith("UPDATE privacy_storage_deletions"):
            row=next(x for x in self.db.rows if x["id"]==args[-1])
            row["attempted"]=True
            row["deleted"]="deleted_at=now()" in sql
            row["last_error"]=None if row["deleted"] else args[0]
        elif sql.startswith("UPDATE privacy_requests"):
            if all(x.get("deleted") for x in self.db.rows):
                self.db.status="completed"
        else:raise AssertionError("Unrecognized SQL "+sql[:140])
    def fetchone(self):return self.selected
    def executemany(self,sql,rows):
        if "ON CONFLICT (user_id,object_key) DO NOTHING" not in sql:
            raise AssertionError("Outbox has no idempotent constraint")
        self.new=list(rows)

class ErasureTests(unittest.TestCase):
    def test_other_users_or_malformed_keys_cannot_be_queued(self):
        storage=FakeStorage()
        self.assertEqual(normalize_object_keys([KEY,KEY],17,storage),[KEY])
        for key in ("uploads/18/2026/10/"+"a"*32+".pdf",
                    "uploads/17/../safe.pdf",
                    "https://evil.example/file",None,""):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    normalize_object_keys([key],17,storage)
    def test_same_transaction_enqueue_before_any_original_reference_lost(self):
        cur=FakeCursor(FakeDb([]))
        self.assertEqual(enqueue_deletions(cur,9,17,[KEY]),1)
        self.assertEqual(cur.new,[(9,17,KEY)])
    def test_success_marks_request_complete(self):
        db=FakeDb([{"id":1,"user_id":17,"privacy_request_id":9,
                    "object_key":KEY}])
        result=drain_pending(lambda:db,FakeStorage())
        self.assertEqual(result,{"processed":1,"deleted":1,"failed":0})
        self.assertEqual(db.status,"completed")
        self.assertEqual(db.commits,2)  # object transaction plus final reconciliation
        self.assertTrue(db.closed)
    def test_failed_delete_does_not_claim_completion(self):
        db=FakeDb([{"id":1,"user_id":17,"privacy_request_id":9,"object_key":KEY}])
        result=drain_pending(lambda:db,FakeStorage("failure"))
        self.assertEqual(result["failed"],1)
        self.assertEqual(db.status,"in_progress")
        self.assertEqual(db.rows[0]["last_error"],"delete_unconfirmed")
        self.assertFalse(db.rows[0].get("deleted"))
    def test_missing_file_404_is_confirmed_erased(self):
        db=FakeDb([{"id":1,"user_id":17,"privacy_request_id":9,"object_key":KEY}])
        result=drain_pending(lambda:db,FakeStorage("already_deleted"))
        self.assertEqual(result["deleted"],1)
        self.assertEqual(db.status,"completed")
    def test_batch_completion_requires_every_file(self):
        other="uploads/17/2026/10/"+"b"*32+".pdf"
        db=FakeDb([{"id":1,"user_id":17,"privacy_request_id":9,"object_key":KEY},
                   {"id":2,"user_id":17,"privacy_request_id":9,"object_key":other}])
        result=drain_pending(lambda:db,FakeStorage(),max_items=1)
        self.assertEqual(result["deleted"],1)
        self.assertEqual(db.status,"in_progress")
    def test_unconfigured_worker_never_starts(self):
        for env,project,enabled in [
            ("production","b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4","enabled"),
            ("preview","545f4c0e-579e-471e-9446-299766efd022","enabled"),
            ("preview","b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4","off")
        ]:
            with patch("minjaz_privacy_storage.threading.Thread") as thread:
                self.assertFalse(start_preview_worker(lambda:None,FakeStorage(),env,project,enabled))
                thread.assert_not_called()
    def test_end_to_end_deletion_never_silently_ignores_failed_storage(self):
        src=(ROOT/"server.py").read_text("utf-8")
        start=src.index("def execute_account_deletion(")
        end=src.index("\ndef update_privacy_request(",start)
        block=src[start:end]
        self.assertIn('enqueue_deletions(cur,int(pid),uid,storage_keys)',block)
        self.assertIn('from upload_intents where user_id=%s',block)
        self.assertIn("final_status='in_progress' if storage_keys else 'completed'",block)
        self.assertNotIn("BUCKET_STORAGE.delete(key)",block)
        self.assertIn("storage_deletion_pending",src)
        self.assertIn("PRIVACY_STORAGE_WORKER",src)
        self.assertIn("privacy_storage_deletions",src)
        self.assertIn("privacy_account_deletion','ok':False",src)
        migration=(ROOT/"database/migrations/042_privacy_storage_deletion_queue.sql").read_text("utf-8")
        self.assertIn("UNIQUE (user_id,object_key)",migration)

if __name__=="__main__":unittest.main()
