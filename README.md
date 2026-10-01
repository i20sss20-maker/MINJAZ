# MINJAZ

مستودع **مِنجاز — MINJAZ** الرسمي.

## Current release

- Version: **0.5.5-rc5**
- Runtime: Python 3.12 + PostgreSQL
- Production service: `minjaz-app-prod`
- Public URL: https://minjaz-app-prod-production.up.railway.app
- Source of truth: GitHub `main`
- Build: Dockerfile from direct source files
- Health check: `/health`
- Readiness check: `/readiness`

## Source layout

- `server.py` — backend/API and marketplace workflows
- `public/index.html` — Arabic RTL web/PWA UI
- `migrate.py` — database migration runner
- `database/migrations/` — ordered PostgreSQL migrations
- `storage.py` — upload validation and S3-compatible presigned storage support

Legacy runtime chunks remain only as repository history/fallback artifacts and are excluded from Docker builds.

## Implemented product flows

MINJAZ currently includes authentication/session management, client and freelancer roles, profiles, service catalog, task creation, proposals, order creation, payment state, delivery, revisions, completion, reviews, messaging, notifications, favorites/team, freelancer discovery, earnings/payout requests, cancellation requests, disputes, support, privacy requests, safety/reporting, admin operations, account activity/security, and PWA assets.

## Deployment safety

Production deploys are built directly from GitHub. Docker build validates:

- backend source size and Python compilation
- frontend bundle presence
- health endpoint presence
- all 10 database migrations

Railway also performs `/health` checks before a deployment is considered healthy.

A separate production probe validates the live public service for database health, beta readiness, catalog access, UI/PWA delivery, CORS restrictions, and security headers.

## Launch status

The application is **beta-ready** on real PostgreSQL infrastructure.

Commercial launch remains intentionally blocked until real external providers are configured for:

- SMS OTP delivery
- payment gateway + signed webhooks
- KYC/identity verification
- S3-compatible object storage credentials

The backend already contains adapters and readiness checks for these integrations. Do not switch `APP_ENV` to `production` until `/readiness` reports `ready_for_commercial_launch: true`.

## Development rule

New functionality should be implemented in the direct source files above. Do not restore the old environment-variable runtime packaging or chunk-reconstruction deployment model.
