# MINJAZ verified account onboarding (sandbox only)

## Approved registration journey

1. Choose **Client** or **Freelancer**.
2. Enter **full name**, **Saudi mobile number**, **email address**, and **password** (10–128 characters).
3. The server stores a unique email identity, a salted `scrypt` password digest, and a random one-use activation link. The new account is **unverified** and cannot sign in or order.
4. The system sends **one email link**, valid for **24 hours**. Opening it validates email ownership and enables the account.
5. Log in with **email + password**. There is **no OTP required at every login**.
6. Forgotten passwords use a **separate one-use email reset link**, valid for **30 minutes**. Reset invalidates old browser sessions.
7. If the activation email is lost, the user can request another activation email; earlier links are invalidated.
8. The protected preview APIs reject browser sessions from legacy accounts with no verified email or incomplete profiles. Legacy phone identities are preserved in the database but not silently merged into new accounts.

## Administrator safety

Set `ADMIN_EMAIL` to the intended administrator mailbox. The owner registers with that exact email and verifies it; only then is the admin role enabled. Passwordless legacy OTP accounts and generic customer signups **cannot** grant admin access. An administrator email change disables the old allowlisted admin's preview access.

## Required Railway sandbox variables

Choose **one** email transport (do not commit secrets to GitHub):

**Resend** (domain-verified sending):

```text
EMAIL_MODE=resend
EMAIL_FROM=no-reply@your-verified-domain.example
RESEND_API_KEY=(secret supplied by Resend)
ADMIN_EMAIL=the-owners-existing-mailbox@example.com
AUTH_SECRET=(strong pre-existing random secret)
PUBLIC_BASE_URL=https://minjaz-digital-services-api-sandbox.up.railway.app
```

**SMTP with STARTTLS or SSL:**

```text
EMAIL_MODE=smtp
EMAIL_FROM=no-reply@your-domain.example
SMTP_HOST=your-smtp-host.example
SMTP_PORT=587
SMTP_USERNAME=(secret)
SMTP_PASSWORD=(secret)
ADMIN_EMAIL=the-owners-existing-mailbox@example.com
```

Never use a fixed verification code, log passwords, or include raw activation/reset tokens in an API response. Until the sender is configured, signups return `503 email_not_configured` rather than generating unusable accounts or bypassing verification.

## API routes

- `GET /api/v1/auth/account-status`: unprivileged readiness state, no secrets.
- `POST /api/v1/auth/register` `{name,phone,email,password,role}`.
- `POST /api/v1/auth/confirm-email` `{token}`.
- `POST /api/v1/auth/resend-verification` `{email}`.
- `POST /api/v1/auth/login-email` `{email,password}`.
- `POST /api/v1/auth/forgot-password` `{email}`.
- `POST /api/v1/auth/reset-password` `{token,password}`.

Existing SMS/email-OTP APIs respond `410 email_registration_required` **on preview only**. No production authorization or payment flows are modified.

## Before using with customers

Run CI unit tests and `scripts/test_minjaz_accounts_postgres.py` against the isolated CI PostgreSQL database. Verify the first real activation email with a test mailbox, verify the resend link and password reset, test both customer and freelancer workflows, and validate admin authorization. Review any legacy-account migration separately before production; matching a phone number alone is **not** proof of ownership.
