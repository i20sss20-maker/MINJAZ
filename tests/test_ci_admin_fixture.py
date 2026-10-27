"""Prove the CI administrator test fixture fails closed without touching a database."""
import unittest
from ci_admin_fixture import require_isolated_ci

class CiAdminFixtureSafetyTests(unittest.TestCase):
    def setUp(self):
        self.env={
            "CI":"true","E2E_CI_ADMIN_FIXTURE":"1","APP_ENV":"beta",
            "EMAIL_AUTH_REQUIRED":"0","SMS_MODE":"dev","PAYMENT_MODE":"mock",
            "ADMIN_PHONE":"+966599999995",
            "AUTH_SECRET":"ci-auth-secret-at-least-32-characters-long",
            "E2E_BASE_URL":"http://127.0.0.1:3000",
            "DATABASE_URL":"postgresql://minjaz:minjaz@127.0.0.1:5432/minjaz",
        }

    def test_only_isolated_ci_is_allowed(self):
        self.assertTrue(require_isolated_ci(self.env,phone=self.env["ADMIN_PHONE"]))
        self.assertTrue(require_isolated_ci({**self.env,"PAYMENT_MODE":"adapter"},phone=self.env["ADMIN_PHONE"]))

    def test_refuses_remote_or_incorrect_databases(self):
        for target in (
            "https://minjaz.example.com",
            "http://localhost:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:3000/anything",
            "http://evil@127.0.0.1:3000",
        ):
            with self.subTest(target=target):
                with self.assertRaises(RuntimeError):
                    require_isolated_ci({**self.env,"E2E_BASE_URL":target},phone=self.env["ADMIN_PHONE"])
        for target in (
            "postgresql://minjaz:minjaz@db.example.com:5432/minjaz",
            "postgresql://minjaz:minjaz@127.0.0.1:5432/production",
            "postgresql://postgres:postgres@127.0.0.1:5432/minjaz",
            "postgresql://minjaz@127.0.0.1:5432/minjaz",
        ):
            with self.subTest(db=target):
                with self.assertRaises(RuntimeError):
                    require_isolated_ci({**self.env,"DATABASE_URL":target},phone=self.env["ADMIN_PHONE"])

    def test_requires_explicit_ci_and_demo_only_auth(self):
        for key,value in (
            ("CI","false"),("E2E_CI_ADMIN_FIXTURE","0"),
            ("APP_ENV","production"),("APP_ENV","preview"),
            ("EMAIL_AUTH_REQUIRED","1"),
            ("SMS_MODE","adapter"),("PAYMENT_MODE","live"),
            ("AUTH_SECRET","dev-secret-change-me"),
            ("ADMIN_PHONE","+966500000001")
        ):
            with self.subTest(key=key,value=value):
                with self.assertRaises(RuntimeError):
                    require_isolated_ci({**self.env,key:value},phone="+966599999995")
        with self.assertRaises(RuntimeError):
            require_isolated_ci(self.env,phone="+966511111111")

if __name__=="__main__":
    unittest.main()
