"""No domain required to test the provider, but never send to real users."""
import io
import json
import os
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from scripts.probe_minjaz_resend_sender import (readiness, send_test, main,
    SANDBOX_PROJECT_ID, SANDBOX_ENVIRONMENT_ID, SANDBOX_SERVICE_ID)

CONFIG={
    "RAILWAY_PROJECT_ID":SANDBOX_PROJECT_ID,
    "RAILWAY_ENVIRONMENT_ID":SANDBOX_ENVIRONMENT_ID,
    "RAILWAY_SERVICE_ID":SANDBOX_SERVICE_ID,
    "APP_ENV":"preview",
    "EMAIL_MODE":"resend",
    "EMAIL_FROM":"onboarding@resend.dev",
    "RESEND_API_KEY":"re_"+"secret-for-unit-test",
    "RESEND_TEST_RECIPIENT":"owner@example.com",
    "AUTH_SECRET":"test-secret-must-be-32-chars-long-beyond",
}

class MockSuccess:
    status=200
    def __init__(self): self.read_count=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):self.read_count+=1;return b'{"id":"hidden"}'

class ResendSetupProbeTests(unittest.TestCase):
    def test_preview_only_and_no_secrets(self):
        self.assertTrue(readiness(CONFIG)["ready"])
        denied=readiness({**CONFIG,"APP_ENV":"production","RAILWAY_PROJECT_ID":"other"})
        self.assertFalse(denied["ready"])
        self.assertIn("dedicated_sandbox_project",denied["missing"])
        for name,expected in (("RAILWAY_ENVIRONMENT_ID","dedicated_sandbox_environment"),
                              ("RAILWAY_SERVICE_ID","dedicated_sandbox_service")):
            with self.subTest(name=name):
                self.assertFalse(readiness({**CONFIG,name:"foreign"})["ready"])
                self.assertIn(expected,readiness({**CONFIG,name:"foreign"})["missing"])
        self.assertIn("preview_environment",denied["missing"])
        self.assertNotIn("re_secret",repr(denied))
        self.assertFalse(denied["has_created_mailbox"])

    def test_missing_provider_and_recipient_fail_closed(self):
        for name in ("RESEND_API_KEY","RESEND_TEST_RECIPIENT","EMAIL_MODE","EMAIL_FROM","AUTH_SECRET"):
            with self.subTest(missing=name):
                cfg=CONFIG.copy()
                cfg.pop(name)
                self.assertFalse(readiness(cfg)["ready"])
                with self.assertRaisesRegex(RuntimeError,"sandbox_mail_not_ready"):
                    send_test(cfg,transport=lambda *a,**kw:self.fail("network call forbidden"))

    def test_recipient_is_private_and_test_message_has_no_real_activation(self):
        seen={}
        def transport(request,timeout):
            seen["url"]=request.full_url
            seen["timeout"]=timeout
            seen["headers"]=dict(request.header_items())
            seen["body"]=json.loads(request.data.decode("utf-8"))
            return MockSuccess()
        out=send_test(CONFIG,transport)
        self.assertEqual(out,{"result":"accepted_by_provider","status":200,
                              "inbox_delivery_confirmed":False})
        self.assertEqual(seen["url"],"https://api.resend.com/emails")
        self.assertEqual(seen["body"]["to"],["owner@example.com"])
        self.assertEqual(seen["body"]["from"],"MINJAZ Test <onboarding@resend.dev>")
        self.assertNotIn("#verify-email=",seen["body"]["text"])
        self.assertNotIn("owner@example.com",str(out))
        self.assertNotIn("re_secret",str(out))

    def test_provider_rejection_has_no_response_body(self):
        def bad(req,timeout):
            raise urllib.error.HTTPError(req.full_url,403,"test",{},None)
        self.assertEqual(send_test(CONFIG,bad),{"result":"provider_rejected","status":403,
                                                "reason_code":"unclassified"})

    def test_classifies_restricted_testing_domain_without_exposing_email(self):
        private_message=("You can only send testing emails to your own email address "
                         "(private@example.com). To send emails to other recipients, "
                         "please verify a domain at resend.com/domains.")
        payload=json.dumps({"name":"validation_error","message":private_message}).encode()
        def rejected(req,timeout):
            return_error=urllib.error.HTTPError(req.full_url,403,"Forbidden",{},
                                               io.BytesIO(payload))
            raise return_error
        result=send_test(CONFIG,rejected)
        self.assertEqual(result,{"result":"provider_rejected","status":403,
                                 "reason_code":"test_sender_recipient_mismatch"})
        self.assertNotIn("private@example.com",json.dumps(result))
        self.assertNotIn(CONFIG["RESEND_API_KEY"],json.dumps(result))

    def test_classifies_other_restrictions_without_raw_provider_text(self):
        samples=(
          ("The domain example.invalid is not verified. Please verify a domain.",
           "sender_domain_not_verified_or_restricted"),
          ("API key is restricted to a different domain and not authorized.",
           "sender_domain_not_verified_or_restricted"),
          ("API key permission is restricted.",
           "api_key_restricted_or_invalid"),
          ("Account is restricted from sending email.",
           "provider_account_restricted"),
          ("Unknown error with unexpected@example.com",
           "unclassified"),
        )
        for message,reason in samples:
            with self.subTest(reason=reason):
                def rejected(req,timeout):
                    raise urllib.error.HTTPError(req.full_url,403,"Forbidden",{},
                        io.BytesIO(json.dumps({"message":message}).encode()))
                response=send_test(CONFIG,rejected)
                self.assertEqual(response["reason_code"],reason)
                self.assertNotIn(message,response.__repr__())
                self.assertNotIn("example.com",json.dumps(response))


    def test_dry_run_does_not_contact_external_provider(self):
        with patch("os.environ",CONFIG):
            with patch("urllib.request.urlopen",side_effect=AssertionError("network forbidden")):
                with patch("sys.stdout",new_callable=io.StringIO) as output:
                    self.assertEqual(main([]),0)
                self.assertTrue(json.loads(output.getvalue())["ready"])


    def test_edge_html_403_is_diagnosed_without_leaking_page_or_cf_token(self):
        from email.message import Message
        headers=Message()
        headers["Content-Type"]="text/html; charset=UTF-8"
        headers["CF-Ray"]="secret-edge-identifier-never-log"
        html=b"<html><title>Attention Required! | Cloudflare</title>private@example.com</html>"
        def rejected(req,timeout):
            raise urllib.error.HTTPError(req.full_url,403,"Forbidden",headers,io.BytesIO(html))
        result=send_test(CONFIG,rejected)
        self.assertEqual(result,{"result":"provider_rejected","status":403,
                                 "reason_code":"edge_access_block_suspected"})
        self.assertNotIn("private@example.com",json.dumps(result))
        self.assertNotIn("secret-edge-identifier-never-log",json.dumps(result))
        self.assertNotIn(CONFIG["RESEND_API_KEY"],json.dumps(result))

    def test_plain_html_403_cannot_be_falsely_classified_as_resend_json(self):
        def rejected(req,timeout):
            raise urllib.error.HTTPError(req.full_url,403,"Forbidden",
                {"Content-Type":"text/html"},io.BytesIO(b"<html>Forbidden</html>"))
        result=send_test(CONFIG,rejected)
        self.assertEqual(result["reason_code"],"non_json_403_response")

    def test_cli_dry_run_in_subprocess_resolves_sibling_email_module(self):
        # Reproduces Railway's exact command path, not just importing the
        # module from pytest/unittest (which masks the /app/scripts sys.path).
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(
            [sys.executable, "scripts/probe_minjaz_resend_sender.py"],
            cwd=root, env={**os.environ, **CONFIG},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        self.assertTrue(report["ready"])
        self.assertFalse(report["has_created_mailbox"])
        self.assertNotIn(CONFIG["RESEND_API_KEY"],result.stdout)

    def test_sending_requires_explicit_confirmation(self):
        with patch("os.environ",CONFIG):
            with self.assertRaises(SystemExit):
                main(["--send"])
        self.assertFalse(readiness({**CONFIG,"EMAIL_FROM":"noreply@fake-domain.com"})["ready"])

if __name__=="__main__":
    unittest.main()
