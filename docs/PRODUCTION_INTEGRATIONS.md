# MINJAZ production integrations

This document is the provider contract for moving MINJAZ from beta to commercial production.

## Launch rule

Keep `APP_ENV=beta` until `GET /readiness` reports `ready_for_commercial_launch: true`.

When `APP_ENV=production`, the backend intentionally refuses to start if a required production integration is missing or unsafe.

## SMS OTP adapter

Required variables:

- `SMS_MODE=adapter`
- `SMS_WEBHOOK_URL=https://...`
- `SMS_WEBHOOK_BEARER=<secret, at least 16 chars>`

MINJAZ sends an authenticated HTTPS POST:

```json
{
  "challenge_id": "uuid",
  "phone": "+9665xxxxxxxx",
  "code": "123456",
  "purpose": "login",
  "expires_in_seconds": 600
}
```

The adapter must deliver the SMS and return a successful HTTP response.

## Payment adapter

Required variables:

- `PAYMENT_MODE=adapter`
- `PAYMENT_CREATE_URL=https://...`
- `PAYMENT_ADAPTER_BEARER=<secret, at least 16 chars>`
- `PAYMENT_WEBHOOK_SECRET=<secret, at least 32 chars>`

Checkout creation request:

```json
{
  "order_id": 123,
  "amount": 150.0,
  "currency": "SAR",
  "customer": {
    "phone": "+9665xxxxxxxx",
    "name": "Customer"
  },
  "return_url": "https://<minjaz-host>/#orders",
  "webhook_contract": "minjaz-normalized-v1",
  "webhook_url": "https://<minjaz-host>/api/v1/integrations/payments/webhook"
}
```

Expected adapter response:

```json
{
  "checkout_url": "https://provider.example/checkout/...",
  "provider_payment_id": "provider-id"
}
```

Normalized webhook:

```json
{
  "event_id": "unique-provider-event-id",
  "type": "payment.succeeded",
  "provider_payment_id": "provider-id",
  "order_id": 123,
  "amount": 150.0
}
```

Allowed event types are `payment.succeeded` and `payment.failed`.

Sign the raw webhook body with HMAC-SHA256 using `PAYMENT_WEBHOOK_SECRET` and put the lowercase hex digest in `X-Minjaz-Signature`. The backend deduplicates events, verifies order/provider/amount consistency, and never lets a late failure regress a confirmed payment.

## KYC adapter

Required variables:

- `KYC_MODE=adapter`
- `KYC_START_URL=https://...`
- `KYC_ADAPTER_BEARER=<secret, at least 16 chars>`
- `KYC_WEBHOOK_SECRET=<secret, at least 32 chars>`

Verification start request:

```json
{
  "user_id": 123,
  "phone": "+9665xxxxxxxx",
  "name": "Freelancer",
  "return_url": "https://<minjaz-host>/#account",
  "webhook_contract": "minjaz-kyc-v1",
  "webhook_url": "https://<minjaz-host>/api/v1/integrations/kyc/webhook"
}
```

Expected adapter response:

```json
{
  "verification_url": "https://provider.example/verify/...",
  "provider_reference": "provider-reference"
}
```

Normalized webhook:

```json
{
  "event_id": "unique-provider-event-id",
  "user_id": 123,
  "provider_reference": "provider-reference",
  "status": "approved"
}
```

Allowed statuses are `pending`, `approved`, and `rejected`.

Sign the raw body with HMAC-SHA256 using `KYC_WEBHOOK_SECRET` and send the lowercase hex digest in `X-Minjaz-Signature`.

## Object storage

Required application variables:

- `STORAGE_MODE=railway_bucket`
- `BUCKET`
- `ACCESS_KEY_ID`
- `SECRET_ACCESS_KEY`
- `REGION`
- `ENDPOINT`
- `BUCKET_URL_STYLE=virtual`

Optional:

- `MAX_UPLOAD_BYTES` — defaults to 50 MB.

The app already supports presigned direct uploads, upload completion verification, file extension/MIME allowlisting, per-user object keys, attachment consumption, and private presigned downloads.

## Commercial launch checklist

1. Configure real SMS OTP delivery.
2. Configure payment checkout and signed payment webhooks.
3. Configure KYC verification and signed KYC webhooks.
4. Configure the S3-compatible storage bucket.
5. Complete final legal review of Terms, Privacy Policy, marketplace rules, cancellation/refund wording, and provider disclosures.
6. Confirm `/readiness` reports commercial readiness.
7. Run the Production Smoke workflow successfully.
8. Change `APP_ENV` to `production`.
