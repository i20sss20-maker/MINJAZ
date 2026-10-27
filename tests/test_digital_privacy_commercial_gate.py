"""Strict public commercial readiness must include verified account-deletion privacy."""
import unittest
from unittest.mock import patch
from scripts import check_minjaz_launch_readiness as readiness

BASE="https://minjaz.example.com"

def response(path,privacy=None):
    if path=="/health":return {"ok":True,"database":True}
    if path=="/readiness":
        checks=[{"key":x,"ok":True,"required":True} for x in (
            "app_environment","authentication_provider","payment_provider",
            "file_storage","kyc_provider","legal_review",
            "marketplace_payout_settlement")]
        if privacy is not None:
            checks.append({"key":"privacy_account_deletion","ok":privacy,"required":True})
        return {"checks":checks,"ready_for_commercial_launch":True}
    if path=="/api/v1/categories":
        return {"items":[{"id":i} for i in range(5)]}
    if path=="/api/v1/services":
        return {"items":[{"id":i+1,"name_ar":"اختبار","category_id":0} for i in range(40)]}
    if path=="/api/v1/auth/account-status":
        return {"enabled":True,"configured":True,"registration":"email_link",
                "fields":["name","email","phone","password"]}
    if path=="/api/v1/me":return {"error":"unauthorized"}
    raise AssertionError("Unexpected endpoint "+path)

class PrivacyCommercialReadinessTests(unittest.TestCase):
    def probe(self,privacy):
        def fake_fetch(base,path,expect=200):
            self.assertEqual(base,BASE)
            if path=="/api/v1/me":self.assertEqual(expect,401)
            return response(path,privacy)
        with patch.object(readiness,"fetch",fake_fetch), patch.object(
                readiness,"check_public_ui",return_value=True):
            return readiness.run(BASE,commercial=True)

    def test_privacy_gate_must_be_present(self):
        with self.assertRaisesRegex(RuntimeError,"account-deletion privacy review incomplete"):
            self.probe(None)

    def test_known_unfixed_privacy_cannot_be_ignored(self):
        with self.assertRaisesRegex(RuntimeError,"account-deletion privacy review incomplete"):
            self.probe(False)

    def test_privacy_gate_is_additional_to_existing_commercial_gates(self):
        result=self.probe(True)
        self.assertTrue(result["ready_for_commercial_launch"])

    def test_probe_rejects_paths_credentials_query_and_bad_ports(self):
        for bad in ("http://minjaz.example.com","https://minjaz.example.com/path",
                    "https://user@minjaz.example.com",
                    "https://minjaz.example.com?redirect=x",
                    "https://minjaz.example.com:garbage"):
            with self.subTest(origin=bad):
                with patch.object(readiness,"fetch",side_effect=AssertionError("Should not fetch")):
                    with self.assertRaisesRegex(RuntimeError,"HTTPS origin"):
                        readiness.run(bad)

if __name__=="__main__":unittest.main()
