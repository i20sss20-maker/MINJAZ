"""Private-object erasure outbox, independent of account/financial operations.

The caller enqueues S3 keys inside the SAME database transaction that anonymizes
the account. This worker processes only keys belonging to that user, retries
failed deletes, and completes the privacy request only once all objects are
confirmed gone. Never returns keys to public callers or logs raw keys.
"""
import time
import threading
import urllib.error
import psycopg2.extras

MAX_BATCH=15
DEFAULT_INTERVAL=120

def normalize_object_keys(rows, user_id, storage):
    """Fail closed on unrecognized or other-account keys."""
    if type(user_id) is not int or user_id<=0:
        raise ValueError("invalid_deleted_user")
    result=set()
    for entry in rows:
        key=str(entry or "").strip()
        if not key or not storage.safe_key_for_user(key,user_id):
            raise ValueError("unsafe_privacy_object_key")
        result.add(key)
    return sorted(result)

def enqueue_deletions(cur, privacy_request_id, user_id, object_keys):
    if not object_keys:return 0
    cur.executemany("""INSERT INTO privacy_storage_deletions
        (privacy_request_id,user_id,object_key)
        VALUES (%s,%s,%s)
        ON CONFLICT (user_id,object_key) DO NOTHING""",
        [(privacy_request_id,user_id,key) for key in object_keys])
    return len(object_keys)

def _object_missing(storage,key):
    """404 from a private HEAD verifies the object was already deleted."""
    try:
        storage.head(key,timeout=8)
        return False
    except urllib.error.HTTPError as exc:
        return exc.code==404
    except Exception:
        return False

def _delete_one(storage, key, user_id):
    if not storage.ready or not storage.safe_key_for_user(key,user_id):
        return False,"unsafe_or_unavailable_storage"
    try:
        if storage.delete(key,timeout=10):return True,None
        if _object_missing(storage,key):return True,None
        return False,"delete_unconfirmed"
    except Exception:
        if _object_missing(storage,key):return True,None
        return False,"storage_unreachable"

def drain_pending(connect, storage, max_items=MAX_BATCH):
    """One DB transaction per deleted object; SKIP LOCKED is replica-safe."""
    limit=max(0,min(int(max_items),MAX_BATCH))
    if not limit or not storage.ready:return {"processed":0,"deleted":0,"failed":0}
    result={"processed":0,"deleted":0,"failed":0}
    db=connect()
    try:
        db.autocommit=False
        for _ in range(limit):
            try:
                with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""SELECT id,user_id,privacy_request_id,object_key
                        FROM privacy_storage_deletions
                        WHERE deleted_at IS NULL
                          AND (last_attempt_at IS NULL OR last_attempt_at < now()-interval '2 minutes')
                        ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED""")
                    item=cur.fetchone()
                    if not item:
                        db.rollback()
                        break
                    result["processed"]+=1
                    success,reason=_delete_one(storage,item["object_key"],int(item["user_id"]))
                    if success:
                        cur.execute("""UPDATE privacy_storage_deletions SET
                            deleted_at=now(),attempts=attempts+1,last_attempt_at=now(),
                            last_error=NULL WHERE id=%s""",(item["id"],))
                        cur.execute("""UPDATE privacy_requests SET
                            status='completed',resolved_at=coalesce(resolved_at,now())
                            WHERE id=%s AND deletion_executed_at IS NOT NULL
                              AND NOT EXISTS (SELECT 1 FROM privacy_storage_deletions
                                 WHERE privacy_request_id=%s AND deleted_at IS NULL)""",
                            (item["privacy_request_id"],item["privacy_request_id"]))
                        result["deleted"]+=1
                    else:
                        cur.execute("""UPDATE privacy_storage_deletions SET
                            attempts=attempts+1,last_attempt_at=now(),last_error=%s
                            WHERE id=%s""",(reason,item["id"]))
                        result["failed"]+=1
                db.commit()
            except Exception:
                db.rollback()
                raise
        return result
    finally:
        db.close()

def start_preview_worker(connect,storage,env,project_id,enabled):
    """Only opt-in on the exact isolated MINJAZ preview Railway project."""
    if (env!='preview' or project_id!='b64c32a3-e7d0-4f5c-8482-c0f43bc1f3f4'
            or enabled!='enabled' or not storage.ready):
        return False
    def loop():
        while True:
            try:
                outcome=drain_pending(connect,storage)
                if outcome["processed"]:
                    print("PRIVACY_STORAGE_ERASURE_BATCH",
                          "processed="+str(outcome["processed"]),
                          "confirmed="+str(outcome["deleted"]),
                          "retry="+str(outcome["failed"]),flush=True)
            except Exception as exc:
                print("PRIVACY_STORAGE_ERASURE_RETRY",type(exc).__name__,flush=True)
            time.sleep(DEFAULT_INTERVAL)
    threading.Thread(target=loop,name="minjaz-privacy-erase",daemon=True).start()
    return True
