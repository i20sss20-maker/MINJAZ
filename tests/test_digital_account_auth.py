"""Email signup/password validation and non-bypass security regression tests."""
import inspect
import os
import unittest
from unittest.mock import patch

from minjaz_account_auth import (clean_phone,valid_password,hash_password,
    verify_password,token_digest,secure_config,register,request_password_reset,
    reset_password,consume_email_link)
from minjaz_email_auth import normalize_email

class UnexpectedDatabase:
    def __call__(self):
        raise AssertionError("No database access expected")

class AccountRegistrationTests(unittest.TestCase):
    SECRET="x"*50
    def test_saudi_phone_normalization(self):
        cases={"0512345678":"+966512345678","512345678":"+966512345678",
               "+966512345678":"+966512345678","00966512345678":"+966512345678"}
        for given,expected in cases.items():
            self.assertEqual(clean_phone(given),expected)
    def test_reject_non_saudi_or_invalid_numbers(self):
        for value in (None,True,"","1234","+971555555555","05000000","0851234567",[],{}):
            with self.subTest(value=value):
                self.assertEqual(clean_phone(value),"")
    def test_email_canonicalization(self):
        self.assertEqual(normalize_email("Example.User@Example.COM"),"example.user@example.com")
        for value in (None,True,"notemail","a@example","a..b@example.com"):
            self.assertEqual(normalize_email(value),"")
    def test_password_length_and_unicode(self):
        self.assertTrue(valid_password("helloWorld11"))
        self.assertTrue(valid_password("كلمة مرور طويلة 123"))
        self.assertFalse(valid_password(""))
        self.assertFalse(valid_password("123456789"))
        self.assertFalse(valid_password("a"*129))
    def test_passwords_are_randomly_salted(self):
        password="strongPassphrase1234!"
        h1=hash_password(password);h2=hash_password(password)
        self.assertNotEqual(h1,h2)
        self.assertTrue(verify_password(password,h1))
        self.assertTrue(verify_password(password,h2))
        self.assertFalse(verify_password("another password123",h1))
        self.assertNotIn(password,h1)
    def test_reject_malformed_password_hash(self):
        for value in (None,"","plaintext","scrypt$1$1$1$abc$bad",123):
            self.assertFalse(verify_password("password12345",value))
    def test_action_token_peppered_hmac(self):
        a=token_digest(self.SECRET,"token_one")
        b=token_digest(self.SECRET,"token_two")
        self.assertNotEqual(a,b);self.assertEqual(len(a),64)
        self.assertNotIn("token_one",a)
    def test_delivery_requirements_must_be_usable(self):
        good={"AUTH_SECRET":"x"*50,"PUBLIC_BASE_URL":"https://preview.example.com",
              "EMAIL_MODE":"resend","EMAIL_FROM":"hello@example.com",
              "RESEND_API_KEY":"re_"+"x"*22}
        self.assertTrue(secure_config(good))
        for key,bad in (("AUTH_SECRET","dev-secret-change-me"),
                        ("PUBLIC_BASE_URL","http://preview.example.com"),
                        ("EMAIL_MODE","off"),("EMAIL_FROM",""),("RESEND_API_KEY","")):
            with self.subTest(key=key):
                self.assertFalse(secure_config({**good,key:bad}))
    def test_unconfigured_email_blocks_signup_without_database(self):
        code,data=register({"name":"أحمد","email":"person@example.com",
            "phone":"0512345678","password":"myPass123456","role":"client"},
            UnexpectedDatabase(),self.SECRET,ready=False)
        self.assertEqual(code,503)
        self.assertEqual(data["error"],"email_not_configured")
    def test_all_registration_fields_required(self):
        base={"name":"صالح مساعد","email":"saleh@example.com",
              "phone":"0512345678","password":"strongPassphrase12345","role":"client"}
        for field,value in (("name","A"),("email","bad"),("phone","1234"),
                            ("password","short"),("role","admin")):
            with self.subTest(field=field):
                code,data=register({**base,field:value},UnexpectedDatabase(),self.SECRET,
                                   ready=True)
                self.assertEqual(code,400)
                self.assertTrue(data["error"].startswith("invalid_"))
    def test_invalid_email_action_token_does_not_hit_db(self):
        for token in (None,45,"","a"*5,"<script>"):
            code,_=consume_email_link({"token":token},UnexpectedDatabase(),self.SECRET,"")
            self.assertEqual(code,400)
            code,_=reset_password({"token":token,"password":"Password1234!"},
                                  UnexpectedDatabase(),self.SECRET)
            self.assertEqual(code,400)
    def test_unconfigured_recovery_cannot_send(self):
        code,_=request_password_reset({"email":"test@example.com"},UnexpectedDatabase(),
                                      self.SECRET,ready=False)
        self.assertEqual(code,503)
    def test_correct_password_required_to_use_login_endpoint(self):
        server=(__import__("pathlib").Path(__file__).resolve().parents[1]/"server.py").read_text()
        self.assertIn("/api/v1/auth/login-email",server)
        self.assertIn("email_verified_at",server)
        self.assertIn("email_registration_required",server)
        self.assertIn("EMAIL_AUTH_REQUIRED=(APP_ENV=='preview'",server)
        self.assertIn("if row and EMAIL_AUTH_REQUIRED:",server)
        self.assertIn("if not EMAIL_AUTH_REQUIRED:",server)
        self.assertIn("if EMAIL_AUTH_REQUIRED:",server)
        self.assertIn("blockers.append('EMAIL_PROVIDER')",server)
        self.assertIn("'enabled':EMAIL_AUTH_REQUIRED",server)

if __name__=="__main__":
    unittest.main()
