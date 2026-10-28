# MINJAZ official launch gate — 2026-10-28

**Status: NOT AUTHORIZED FOR COMMERCIAL LAUNCH.** Do not describe `beta.minjazapp.com` or the old Railway `minjaz-app-prod` as a fully active customer-paid marketplace.

## Verified Railway inventory (read-only)
- Isolated working sandbox: `MINJAZ-DIGITAL-SERVICES-TEST`; API and PostgreSQL 18 deployed successfully with authenticated account workflows and private S3 uploads. Daily backup cron deployed but independent restored-data drill is still outstanding.
- Existing legacy production: `MINJAZ` (`545f4c0e-579e-471e-9446-299766efd022`), environment `production`, `minjaz-app-prod` on GitHub `main`, Postgres 16 service. Current production environment inventory exposes **no mounted persistent volumes or provisioned object buckets**. Its service has **23 staged destructive service deletions**, which must NOT be committed without a manual recovery review. Do not call `accept_deploy` on that environment.
- The configured production app lacks verified domain email sender credentials and the independent marketplace payout integration required by the latest preview source. Those credentials cannot safely be copied from the isolated sandbox without the owner or provider taking the normal secret setup steps.
- New preview code refuses `APP_ENV=production` until its hard provider checks pass, including a separate verified marketplace payout/settlement integration. No configuration variable can safely declare that provider implemented when it is not.

## Official release blockers and owners
1. **Business/legal** (owner + qualified legal reviewer): identify the actual business operator, applicable registration/authorization, and approve marketplace contracts, privacy notices, cancellation/refund and dispute policies. Check Saudi PDPL and cross-border personal-data storage/transfer obligations for Railway AMS (Netherlands), and operational retention/erasure.
2. **Payments** (licensed PSP): integrate live transaction creation, signed webhooks, refund confirmations, *marketplace provider-controlled split settlements or transfers to freelancers*, reconciliation and idempotent audit. An App Store/Google Play digital subscription does not provide a freelancer payout service. No dummy paid flag or user-to-user wallet.
3. **Identity** (qualified vendor): integrate actual freelancer identity/age/beneficiary checks via signed KYC callbacks; do not show `approved` based on manual or demo records.
4. **Production infrastructure**: inventory & preserve legacy production data; resolve its 23 destructive staged changes without blind approval, create separate persistent production PostgreSQL and external backup strategy, run a restore drill into a disposable instance, set dedicated production S3 bucket & access, production AUTH_SECRET, and own-domain transactional email secrets. No data migration from preview before consent, validation, and duplication audit.
5. **Privacy**: scrub credentials on approved account deletion; verify object deletion, retention/legal holds and end-to-end deletion. Until storage erasure is proven, `privacy_account_deletion.ok=false` is deliberately mandatory.
6. **Release validation**: production `/health`, `/readiness` and read-only `scripts/check_minjaz_launch_readiness.py --commercial` must pass; independent smoke tests of role isolation and storage; domain `minjazapp.com` ownership/HTTPS, DNS, cookies, CORS, monitoring, incident response and rollback.

## Production cutover rules
- Never flip `APP_ENV` on the preview server just to make the browser display "official".
- Never apply the existing destructive Railway production patch en masse.
- Never expose unapproved payments or imply an order is paid when the provider has not confirmed it.
- Do not repoint the root domain or send broad invitations until provider, legal and data protection gates are satisfied and a separate production deployment passes healthchecks.
- If launching a *nonfinancial* public directory first, it requires an explicit scoped legal review and separate product controls preventing paid/contractual commitments. It is not a substitute for commercial launch.
