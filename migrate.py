import hashlib
import os
import time
from pathlib import Path
import psycopg2

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
DB = dict(
    host=os.getenv('PGHOST'),
    port=int(os.getenv('PGPORT', '5432')),
    user=os.getenv('PGUSER'),
    password=os.getenv('PGPASSWORD'),
    dbname=os.getenv('PGDATABASE'),
)
if not DATABASE_URL:
    missing=[k for k,v in [('PGHOST',DB['host']),('PGUSER',DB['user']),('PGPASSWORD',DB['password']),('PGDATABASE',DB['dbname'])] if not v]
    if missing:
        raise RuntimeError('Missing database configuration: set DATABASE_URL or '+','.join(missing))
MIGRATIONS = Path(__file__).parent / 'database' / 'migrations'
LOCK_KEY = 'minjaz_schema_migrations_v1'


def connect_with_retry(attempts=30, delay=2):
    last = None
    for i in range(attempts):
        try:
            c = psycopg2.connect(DATABASE_URL) if DATABASE_URL else psycopg2.connect(**DB)
            c.autocommit = False
            return c
        except Exception as exc:
            last = exc
            if i == attempts - 1:
                break
            time.sleep(delay)
    raise last


def checksum(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main():
    files = sorted(MIGRATIONS.glob('*.sql'))
    if not files:
        raise SystemExit('No migrations found')
    conn = connect_with_retry()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (LOCK_KEY,))
            cur.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations(
                    version TEXT PRIMARY KEY,
                    checksum TEXT,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            ''')
            cur.execute('ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT')
        conn.commit()

        for path in files:
            version = path.name
            sql = path.read_text(encoding='utf-8')
            digest = checksum(sql)
            with conn.cursor() as cur:
                cur.execute('SELECT checksum FROM schema_migrations WHERE version=%s', (version,))
                row = cur.fetchone()
            if row:
                existing = row[0]
                if existing and existing != digest:
                    raise RuntimeError(f'Applied migration changed: {version}')
                if not existing:
                    with conn.cursor() as cur:
                        cur.execute('UPDATE schema_migrations SET checksum=%s WHERE version=%s', (digest, version))
                    conn.commit()
                print(f'[migrate] skip {version}')
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)', (version, digest))
                conn.commit()
                print(f'[migrate] applied {version}')
            except Exception:
                conn.rollback()
                raise
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
            conn.commit()
        except Exception:
            pass
        conn.close()


if __name__ == '__main__':
    main()
