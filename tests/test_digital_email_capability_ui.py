"""Email UI must reflect actual server capability without blocking existing logins."""
import unittest
from pathlib import Path

PAGE=(Path(__file__).resolve().parents[1]/
      "public/minjaz-account-registration-v1.js").read_text("utf-8")

class EmailCapabilityUiTests(unittest.TestCase):
    def test_no_false_signup_promises_when_flag_disabled(self):
        self.assertIn('function applyEmailCapability(info)',PAGE)
        self.assertIn('emailCapability=info;',PAGE)
        self.assertIn('if(!enabled){',PAGE)
        self.assertIn('تسجيل الدخول بالبريد غير مفعّل',PAGE)
        self.assertIn('signup.disabled=!enabled||!senderReady',PAGE)
        self.assertIn('login.disabled=!enabled',PAGE)
        self.assertIn('recover.disabled=!enabled||!senderReady',PAGE)
        self.assertIn('reset.disabled=!enabled',PAGE)
        self.assertIn('resendActivationLogin").disabled=!enabled||!senderReady',PAGE)
        self.assertIn('forgotAccountPassword").disabled=!enabled||!senderReady',PAGE)
        self.assertIn('email_registration_disabled:',PAGE)

    def test_login_still_available_after_mail_sender_failure(self):
        self.assertIn('function canSubmitEmailForm(form)',PAGE)
        self.assertIn('form.id==="existingAccountForm"||form.id==="accountResetForm"',PAGE)
        self.assertIn('if(btn)btn.disabled=!canSubmitEmailForm(form)',PAGE)
        self.assertIn('ويمكن لأصحاب الحسابات المفعّلة تسجيل الدخول',PAGE)

    def test_single_use_activation_link_not_overwritten(self):
        self.assertIn('if(window.location.hash || resetToken || $("accountStatus").textContent)return;',PAGE)
        self.assertIn('consumeActionLink();',PAGE)
        self.assertIn('returnToStoreAfterLogin();',PAGE)
        self.assertIn('credentials:"same-origin"',PAGE)

if __name__=="__main__": unittest.main()
