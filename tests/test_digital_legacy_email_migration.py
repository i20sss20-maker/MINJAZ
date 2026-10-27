"""Read-only legacy account inventory must not expose contacts or mutate rows."""
import unittest

from scripts.audit_minjaz_legacy_accounts import audit_counts, REQUIRED_COLUMNS, BLOCKED

class FakeCursor:
    def __init__(self, schemas, rows):
        self.schemas=schemas
        self.rows=iter(rows)
        self.sql=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql):
        self.sql.append(sql)
        if sql.startswith("SET TRANSACTION"):return
        if not sql.lstrip().upper().startswith("SELECT"):
            raise AssertionError("read-only audit issued write SQL")
    def fetchall(self):return self.schemas
    def fetchone(self):return next(self.rows)

class FakeConnection:
    def __init__(self, schemas, rows):
        self.cur=FakeCursor(schemas,rows)
        self.rolled_back=False
        self.closed=False
    def cursor(self):return self.cur
    def rollback(self):self.rolled_back=True
    def close(self):self.closed=True

class LegacyMigrationAuditTests(unittest.TestCase):
    def setUp(self):
        self.schema=[(t,c) for t,cols in REQUIRED_COLUMNS.items() for c in cols]

    def test_reports_aggregate_only_and_blocks_legacy_accounts(self):
        db=FakeConnection(self.schema,[ (5,1,2,1,2,1,1,2), (1,) ])
        report=audit_counts(lambda:db)
        self.assertTrue(db.rolled_back and db.closed)
        self.assertEqual(report["counts"]["active_accounts"],5)
        self.assertEqual(report["counts"]["blocked_by_email_only"],2)
        self.assertEqual(report["counts"]["blocked_with_active_sessions"],1)
        self.assertIsNone(report["counts"]["blocked_with_orders"])
        self.assertTrue(report["account_migration_required"])
        self.assertEqual(report["email_policy_switch_account_gate"],"blocked")
        self.assertFalse(report["contains_personal_data"])
        self.assertFalse(report["writes_performed"])
        self.assertEqual(len(db.cur.sql),4)
        self.assertTrue(db.cur.sql[0].startswith("SET TRANSACTION"))
        self.assertIn("READ ONLY",db.cur.sql[0])
        self.assertNotIn("SELECT u.email,",str(db.cur.sql))
        self.assertNotIn("SELECT phone",str(db.cur.sql))

    def test_includes_order_impact_without_returning_order_ids(self):
        schema=self.schema+[("orders","client_id"),("orders","freelancer_id")]
        db=FakeConnection(schema,[(5,0,0,0,0,0,0,0),(0,),(0,)])
        report=audit_counts(lambda:db)
        self.assertFalse(report["account_migration_required"])
        self.assertEqual(report["counts"]["blocked_with_orders"],0)
        self.assertEqual(report["email_policy_switch_account_gate"],
                         "no_incompatible_active_accounts_detected")
        self.assertIn("EXISTS (",db.cur.sql[-1])
        self.assertTrue(db.rolled_back and db.closed)

    def test_fails_closed_before_migration_034_035(self):
        old=[(t,c) for t,cols in REQUIRED_COLUMNS.items()
             for c in cols if c not in ("email","password_hash","email_verified_at")]
        db=FakeConnection(old,[])
        with self.assertRaisesRegex(RuntimeError,"account_email_schema_not_ready"):
            audit_counts(lambda:db)
        self.assertTrue(db.rolled_back and db.closed)
        self.assertEqual(len(db.cur.sql),2)

    def test_cannot_return_identifiers_or_per_account_rows(self):
        for forbidden in ("SELECT id FROM users","SELECT email FROM users",
                          "SELECT phone FROM users","UPDATE users","DELETE FROM users"):
            self.assertNotIn(forbidden,BLOCKED.upper())

if __name__=="__main__":unittest.main()
