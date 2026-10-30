#!/usr/bin/env python3
"""Isolated PG contract for privacy deletion outbox. No live credentials accepted."""
import os, sys
from pathlib import Path
from urllib.parse import urlparse
import psycopg2
from minjaz_privacy_storage import enqueue_deletions,drain_pending,normalize_object_keys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=os.environ.get("DIGITAL_TEST_DATABASE_URL","")
url=urlparse(SOURCE)
if (os.environ.get("CI")!="true" or url.scheme not in ("postgres","postgresql")
    or url.hostname not in ("127.0.0.1","localhost") or url.port!=5432
    or url.username!="postgres" or url.path!="/digital_test"):
    raise SystemExit("PRIVACY_TEST_REFUSED: expected local CI database only")
TEST_DB="minjaz_privacy_queue_ci"

class TestStorage:
    ready=True
    def __init__(self,succeed):self.succeed=succeed
    def safe_key_for_user(self,key,user):
        import re
        return bool(re.fullmatch(r'uploads/'+str(user)+r'/2026/10/[a-f0-9]{32}\.pdf',key))
    def delete(self,key,timeout=10):return self.succeed
    def head(self,key,timeout=8):return {"size_bytes":100}

def connect():
    return psycopg2.connect(SOURCE.replace("/digital_test","/"+TEST_DB),connect_timeout=5)

def main():
    admin=psycopg2.connect(SOURCE,connect_timeout=5)
    admin.autocommit=True
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s",(TEST_DB,))
            if cur.fetchone():
                raise RuntimeError("PRIVACY_TEST_REFUSED existing database; never overwrite")
            cur.execute("CREATE DATABASE "+TEST_DB)
        with connect() as db:
            with db.cursor() as cur:
                cur.execute("""CREATE TABLE users(id BIGINT PRIMARY KEY);
                               CREATE TABLE privacy_requests(
                                id BIGINT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),
                                request_type TEXT NOT NULL,status TEXT NOT NULL,
                                deletion_executed_at TIMESTAMPTZ,resolved_at TIMESTAMPTZ);
                               INSERT INTO users(id) VALUES (17),(18);
                               INSERT INTO privacy_requests(id,user_id,request_type,status,deletion_executed_at)
                                VALUES(9,17,'delete','in_progress',now());""")
                cur.execute((ROOT/"database/migrations/042_privacy_storage_deletion_queue.sql").read_text("utf-8"))
                key="uploads/17/2026/10/"+"a"*32+".pdf"
                keys=normalize_object_keys([key,key],17,TestStorage(False))
                assert keys==[key]
                assert enqueue_deletions(cur,9,17,keys)==1
        result=drain_pending(connect,TestStorage(False))
        assert result=={"processed":1,"deleted":0,"failed":1},result
        with connect() as db:
            with db.cursor() as cur:
                cur.execute("SELECT status,resolved_at FROM privacy_requests WHERE id=9")
                status,resolved=cur.fetchone()
                assert status=="in_progress" and resolved is None,(status,resolved)
                cur.execute("SELECT attempts,deleted_at FROM privacy_storage_deletions WHERE privacy_request_id=9")
                attempts,deleted=cur.fetchone()
                assert attempts==1 and deleted is None
                # Make the attempt eligible for an isolated simulated retry.
                cur.execute("UPDATE privacy_storage_deletions SET last_attempt_at=now()-interval '3 minutes' WHERE privacy_request_id=9")
        result=drain_pending(connect,TestStorage(True))
        assert result=={"processed":1,"deleted":1,"failed":0},result
        with connect() as db:
            with db.cursor() as cur:
                cur.execute("SELECT status,resolved_at FROM privacy_requests WHERE id=9")
                status,resolved=cur.fetchone()
                assert status=="completed" and resolved is not None,(status,resolved)
                cur.execute("SELECT attempts,deleted_at,last_error FROM privacy_storage_deletions WHERE privacy_request_id=9")
                attempts,deleted,error=cur.fetchone()
                assert attempts==2 and deleted is not None and error is None,(attempts,deleted,error)
                cur.execute("SELECT count(*) FROM privacy_storage_deletions WHERE user_id=18")
                assert cur.fetchone()[0]==0
        print("PRIVACY_STORAGE_POSTGRES_OK isolated_db=yes retry_confirmed=yes finalization_after_s3=yes")
    finally:
        # The DB is created exclusively in this temporary CI instance.
        with admin.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",(TEST_DB,))
            cur.execute("DROP DATABASE IF EXISTS "+TEST_DB)
        admin.close()

if __name__=="__main__":main()
