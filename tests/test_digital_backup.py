"""The backup cron must be read-only, private, and refuse unsafe targets."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
SH=(ROOT/'scripts'/'backup_minjaz_sandbox.sh').read_text(encoding='utf-8')
DOCKER=(ROOT/'Dockerfile.backup').read_text(encoding='utf-8')
DRILL=(ROOT/'scripts'/'restore_drill_minjaz_ci.sh').read_text(encoding='utf-8')


class BackupContract(unittest.TestCase):
    def test_shell_valid(self):
        subprocess.run(['sh','-n',str(ROOT/'scripts'/'backup_minjaz_sandbox.sh')],
                       check=True)

    def test_busybox_compatible_backup_tempfile(self):
        # postgres:18-alpine uses BusyBox mktemp, which rejects suffix templates.
        self.assertIn('mktemp /tmp/minjaz-preview-XXXXXXXX)', SH)
        self.assertNotIn('XXXXXXXX.dump', SH)

    def test_postgres_major_matches_sandbox(self):
        self.assertIn('FROM postgres:18-alpine',DOCKER)
        self.assertIn('aws-cli',DOCKER)
        self.assertIn('backup_minjaz_sandbox.sh',DOCKER)
        self.assertIn('pg_dump --version',SH)

    def test_read_only_private_verified(self):
        for needle in ('APP_ENV" != "preview"', 'https://*',
                       'pg_dump --dbname=', '--format=custom',
                       '--no-owner --no-privileges', 'pg_restore --list',
                       's3api put-object', 's3api head-object',
                       'sha256sum', 'BACKUP_OK', 'BACKUP_REFUSED',
                       'remote_size" != "$size"', 'remote_sha" != "$sha"'):
            self.assertIn(needle,SH)
        self.assertIn('umask 077',SH)
        self.assertIn('mktemp',SH)
        self.assertIn('No automatic deletion',SH)


    def test_disposable_pg18_restore_drill_is_available(self):
        script=ROOT/'scripts'/'restore_drill_minjaz_ci.sh'
        subprocess.run(['bash','-n',str(script)],check=True)
        for term in (
            'postgres:18-alpine',
            'DATABASE_URL PGHOST BACKUP_ENDPOINT AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY',
            'mktemp -d',
            'trap cleanup EXIT',
            'pg_dump -U drill',
            'pg_restore --list',
            'pg_restore --exit-on-error',
            'createdb -U drill minjaz_restore_drill_ci',
            'source_hash',
            'restored_hash',
            'RESTORE_DRILL_OK',
            'synthetic local backup',
        ):
            self.assertIn(term,DRILL)
        self.assertNotIn('railway.internal',DRILL)
        self.assertNotIn('s3://',DRILL)
        self.assertNotIn('pg_restore -d minjaz_backup_source',DRILL)

    def test_no_drop_or_live_restore_or_exposed_credentials(self):
        self.assertNotRegex(SH,r'\\b(?:dropdb|createdb|psql|pg_restore\\s+--dbname|rm\\s+-rf)\\b')
        self.assertNotIn('AWS_SECRET_ACCESS_KEY}',SH.split('echo "BACKUP_OK')[1])
        self.assertNotIn('s3api delete-object',SH)
        self.assertNotIn('http://',SH)
        self.assertNotIn('--acl public-read',SH)


if __name__=='__main__':
    unittest.main()
