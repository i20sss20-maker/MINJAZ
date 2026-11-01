#!/usr/bin/env python3
"""Generate a fail-closed, read-only MINJAZ release-evidence summary.

This is NOT an authorization to publish, a store-signing tool, or a payout
integration. Public GETs only. Report contains checkpoint names/booleans
instead of provider tokens, users, phones, cookies or API response values.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

from scripts import check_minjaz_launch_readiness as probe

REQUIRED_KEYS = frozenset({
    "app_environment", "database_persistence", "email_provider",
    "non_test_email_sender", "verified_email_policy",
    "admin_email_configured", "authentication_provider",
    "payment_provider", "marketplace_payout_settlement",
    "privacy_account_deletion", "file_storage", "kyc_provider",
    "source_control", "legal_versions", "legal_review",
    "public_base_url", "cors_origins", "runtime_schema_ensure",
})
NONFINANCIAL_EXCLUSIONS = frozenset({
    "payment_provider", "marketplace_payout_settlement",
})
# These are separate from the backend; a green API must never imply an
# App Store approval, TestFlight upload, device QA or PSP settlement.
INDEPENDENT_EXTERNAL_EVIDENCE = {
    "apple_distribution_signing": "not_verified_by_this_probe",
    "app_store_connect_submission_and_approval": "not_verified_by_this_probe",
    "google_play_aab_signing_and_approval": "not_verified_by_this_probe",
    "real_device_client_freelancer_admin_e2e": "not_verified_by_this_probe",
    "production_legacy_account_migration_audit": "not_verified_by_this_probe",
    "independent_backup_restore_drill": "not_verified_by_this_probe",
    "regulated_marketplace_psp_and_payout_reconciliation": "not_verified_by_this_probe",
}

def summarize(base, readiness, utc_now=None):
    """Never trust a claimed ready flag without independently checking every gate."""
    checks = readiness.get("checks")
    if not isinstance(checks, list):
        raise ValueError("missing_readiness_check_list")
    by_key = {}
    for item in checks:
        if (not isinstance(item, dict) or not isinstance(item.get("key"), str)
                or type(item.get("ok")) is not bool
                or type(item.get("required")) is not bool):
            raise ValueError("malformed_readiness_check")
        key = item["key"]
        if key in by_key:
            raise ValueError("duplicate_readiness_check")
        by_key[key] = item
    missing = sorted(REQUIRED_KEYS - by_key.keys())
    # Fail closed even if a compromised/stale API falsely advertises ready.
    required_false = sorted(
        key for key, value in by_key.items()
        if value["required"] and not value["ok"]
    )
    required_mislabeled = sorted(
        key for key in REQUIRED_KEYS if key in by_key and not by_key[key]["required"]
    )
    environment = str(by_key.get("app_environment", {}).get("value", "unknown"))
    # Environment is an allow-listed label, never raw provider settings.
    environment = environment if environment in ("preview", "beta", "production") else "unknown"
    ready_beta = bool(readiness.get("ready_for_beta") is True and not missing)
    financial_ready = (
        not missing and not required_false and not required_mislabeled
        and environment == "production"
        and readiness.get("ready_for_commercial_launch") is True
    )
    nonfinancial_blockers = sorted(
        key for key in required_false if key not in NONFINANCIAL_EXCLUSIONS
    )
    pilot_ready = (
        not missing and not required_mislabeled and not nonfinancial_blockers
        and environment == "production"
        and by_key.get("payment_provider", {}).get("value") == "off"
        and readiness.get("ready_for_nonfinancial_pilot") is True
    )
    return {
        "generated_at_utc": (utc_now or dt.datetime.now(dt.timezone.utc)).isoformat(),
        "source": base.rstrip("/"),
        "read_only": True,
        "environment": environment,
        "beta_technical_gate": "passed" if ready_beta else "blocked",
        "nonfinancial_pilot_gate": "passed" if pilot_ready else "blocked",
        "commercial_backend_gate": "passed" if financial_ready else "blocked",
        "missing_required_checkpoints": missing,
        "missing_mandatory_labels": required_mislabeled,
        "backend_blockers": required_false,
        "pilot_blockers": nonfinancial_blockers,
        "unverified_external_evidence": INDEPENDENT_EXTERNAL_EVIDENCE.copy(),
        "store_distribution_gate": "not_verified",
        "full_public_launch": "NOT_AUTHORIZED",
        "note": "This probe does not verify Apple/Google store approval, real-device QA, contracts, bank settlement or compliance.",
    }

def make_report(base, check=None):
    # Resolve the dependency on each call so CI can inject a read-only stub
    # without invoking external HTTP while exercising negative test cases.
    # Production behavior still uses the real GET-only probe.
    if check is None:
        check = probe.run
    # Includes HTTPS origin validation, DB health, public page routes, email
    # contract, role isolation and live category+service catalog; no writes.
    readiness = check(base, commercial=False)
    return summarize(base, readiness)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=probe.DEFAULT_BASE)
    ap.add_argument("--output", help="Write non-sensitive JSON for CI artifact")
    ap.add_argument("--require-commercial", action="store_true")
    ap.add_argument("--require-pilot", action="store_true")
    args = ap.parse_args(argv)
    if args.require_commercial and args.require_pilot:
        ap.error("Select only one release gate")
    try:
        report = make_report(args.base)
        serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            dest = pathlib.Path(args.output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(serialized + "\n", encoding="utf-8")
        print(serialized)
        if args.require_commercial:
            return 0 if report["commercial_backend_gate"] == "passed" else 2
        if args.require_pilot:
            return 0 if report["nonfinancial_pilot_gate"] == "passed" else 2
        return 0
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        # Untrusted errors can contain endpoint details. Emit only exception
        # class; no secrets, tokens or customer data in public CI logs.
        print("MINJAZ_RELEASE_EVIDENCE_FAILED", type(exc).__name__, file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
