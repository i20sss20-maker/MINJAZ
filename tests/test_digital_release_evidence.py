"""No-payment beta, verified pilot and commercial launch must not be conflated."""
import unittest
from unittest.mock import patch

from scripts import minjaz_release_evidence as gate

BASE = "https://beta.minjazapp.com"

def response(*, environment="preview", missing=(), false=(), required_override=(), payment="off"):
    rows = []
    for name in sorted(gate.REQUIRED_KEYS):
        if name in missing:
            continue
        val = environment if name == "app_environment" else (
            payment if name == "payment_provider" else "configured")
        rows.append({
            "key": name,
            "ok": name not in false,
            "required": name not in required_override,
            "value": val,
        })
    return {
        "checks": rows,
        "ready_for_beta": True,
        "ready_for_nonfinancial_pilot": True,
        "ready_for_commercial_launch": True,
    }

class ReleaseEvidenceTests(unittest.TestCase):
    def test_preview_cannot_claim_paid_or_unpaid_production_launch(self):
        report = gate.summarize(BASE, response())
        self.assertEqual(report["beta_technical_gate"], "passed")
        self.assertEqual(report["nonfinancial_pilot_gate"], "blocked")
        self.assertEqual(report["commercial_backend_gate"], "blocked")
        self.assertEqual(report["store_distribution_gate"], "not_verified")
        self.assertEqual(report["full_public_launch"], "NOT_AUTHORIZED")
        self.assertTrue(report["unverified_external_evidence"])

    def test_production_backend_pass_does_not_claim_store_approval(self):
        report = gate.summarize(BASE, response(environment="production", payment="adapter"))
        self.assertEqual(report["commercial_backend_gate"], "passed")
        self.assertEqual(report["full_public_launch"], "NOT_AUTHORIZED")
        self.assertEqual(report["store_distribution_gate"], "not_verified")

    def test_production_nonfinancial_pilot_is_distinct_from_financial_launch(self):
        raw = response(environment="production", payment="off",
                       false=("payment_provider", "marketplace_payout_settlement"))
        report = gate.summarize(BASE, raw)
        self.assertEqual(report["nonfinancial_pilot_gate"], "passed")
        self.assertEqual(report["commercial_backend_gate"], "blocked")
        self.assertEqual(report["backend_blockers"],
                         ["marketplace_payout_settlement", "payment_provider"])
        self.assertEqual(report["pilot_blockers"], [])

    def test_no_fake_green_flags_when_check_is_missing_or_unverified(self):
        for item in ("marketplace_payout_settlement", "privacy_account_deletion",
                     "legal_review", "non_test_email_sender", "kyc_provider"):
            with self.subTest(item=item):
                report = gate.summarize(BASE, response(environment="production", missing=(item,)))
                self.assertEqual(report["commercial_backend_gate"], "blocked")
                self.assertIn(item, report["missing_required_checkpoints"])

    def test_false_checkpoint_blocks_pilot_and_commercial_even_if_server_claims_ready(self):
        report = gate.summarize(BASE, response(
            environment="production", false=("privacy_account_deletion",)))
        self.assertEqual(report["commercial_backend_gate"], "blocked")
        self.assertEqual(report["nonfinancial_pilot_gate"], "blocked")
        self.assertIn("privacy_account_deletion", report["pilot_blockers"])

    def test_relabeling_required_checkpoint_as_optional_cannot_bypass(self):
        report = gate.summarize(BASE, response(
            environment="production", required_override=("legal_review",)))
        self.assertEqual(report["commercial_backend_gate"], "blocked")
        self.assertIn("legal_review", report["missing_mandatory_labels"])

    def test_duplicate_and_malformed_server_output_fails_closed(self):
        raw = response()
        raw["checks"].append(raw["checks"][0])
        with self.assertRaisesRegex(ValueError, "duplicate_readiness_check"):
            gate.summarize(BASE, raw)
        raw = response()
        raw["checks"][0]["ok"] = "true"
        with self.assertRaisesRegex(ValueError, "malformed_readiness_check"):
            gate.summarize(BASE, raw)

    def test_never_copy_provider_values_into_artifact(self):
        raw = response(environment="production")
        for x in raw["checks"]:
            if x["key"] == "source_control":
                x["value"] = "secret_DO_NOT_PRINT"
        report = gate.summarize(BASE, raw)
        self.assertNotIn("secret_DO_NOT_PRINT", repr(report))

    def test_probe_is_called_read_only_without_payment_mutations(self):
        raw = response()
        with patch.object(gate.probe, "run", return_value=raw) as fake:
            report = gate.make_report(BASE)
        fake.assert_called_once_with(BASE, commercial=False)
        self.assertTrue(report["read_only"])
        self.assertEqual(report["source"], BASE)

if __name__ == "__main__":
    unittest.main()
