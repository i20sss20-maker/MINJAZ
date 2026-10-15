# MINJAZ Google Play release checklist

## Android
- Production applicationId: sa.minjaz.app
- Preview applicationId: sa.minjaz.preview
- Production versionCode: 14
- Production versionName: 1.0.0-rc4
- Preview versionCode: 13
- Preview versionName: 0.13-back-reliability
- targetSdk: 36
- minSdk: 24
- Cleartext traffic disabled
- Production AAB task: :app:bundleProductionRelease
- Preview APK task: :app:assemblePreviewDebug

## Signing
GitHub Actions expects these repository secrets:
- MINJAZ_ANDROID_KEYSTORE_BASE64
- MINJAZ_ANDROID_KEYSTORE_PASSWORD
- MINJAZ_ANDROID_KEY_ALIAS
- MINJAZ_ANDROID_KEY_PASSWORD

Windows helper:
```powershell
powershell -ExecutionPolicy Bypass -File tools/create-minjaz-production-keystore.ps1
```

If GitHub CLI is installed and authenticated, the helper can configure all four secrets directly:
```powershell
powershell -ExecutionPolicy Bypass -File tools/create-minjaz-production-keystore.ps1 -ConfigureGitHub
```

The keystore is created only under `release-private/`, which is ignored by Git. Back up the JKS file and the two passwords in a secure password manager / offline backup. Do not commit them, upload them to project files, or paste them into chat.

## Android release candidate rc4

- Bound native Android back-button JS handling to a 1.5-second watchdog, with generation checks so late callbacks cannot hijack a later back press.
- Recover through native WebView history or close the activity if the page JS is frozen or throws.
- Back from the full-page connection error no longer reveals the broken WebView error document.
- Cancel pending back callbacks on pause, renderer replacement, new intent, and activity destruction.
- A signed rc4 APK/AAB must be verified from a new Android Release Artifacts CI run before distribution.

## Android release candidate rc3

- Debounce Android Wi-Fi/mobile network callbacks and retry only once the network becomes internet-validated, including transitions from captive Wi-Fi.
- Ignore late page/error callbacks from a replaced WebView renderer so they cannot overwrite the new loading or error view.
- The signed rc3 artifact must be verified from its own CI run. Previous signed rc2 binaries do not include these changes.

## Android release candidate rc2

- Version `1.0.0-rc2` fixes cancellation of pending file input callbacks during picker failures and WebView renderer recovery. Error messages are localized to Arabic and English.
- HTTPS in-app navigation is restricted to the app's real origin; unsupported external URL schemes are blocked from Android intents.
- Google Play release signing for **rc2 must be verified in its own Actions run** before considering it a release candidate. The older signed `1.0.0-rc1` artifact does not contain these fixes.
- Android CI compilation and APK/AAB validation alone do not prove real-device usability or Play approval.

## Verified Android signing baseline (2026-10-05)

- GitHub Actions **Android Release Artifacts** run [37380503030](https://github.com/i20sss20-maker/MINJAZ/actions/runs/37380503030) successfully built and signed **APK and AAB** for production flavor `sa.minjaz.app`, version `1.0.0-rc1` (`versionCode 11`).
- The signed artifact was checked by Android `apksigner` and Java `jarsigner`; the run's ZIP includes both files and SHA-256 hashes. This proves signing at that point in time; do not assume a future release is signed until its own workflow verifies it.
- GitHub Actions artifact `MINJAZ-1.0.0-rc1-production-signed` has a retention expiry of **2026-11-04**. Store final release binaries in an approved release channel before they expire.
- Signing evidence **does not** mean the app has been submitted, approved, or launched on Google Play.

## Commercial launch status (checked 2026-10-14)

`Production Smoke` verified that `/readiness` returned `ready_for_commercial_launch: false`. Required blockers: `app_environment`, `sms_provider`, `payment_provider`, `file_storage`, `kyc_provider`, and `legal_review`.

Maintain `APP_ENV=beta` until all real providers, signed callbacks, private file storage, and legal review are verified and `/readiness` confirms commercial readiness. Do not use the existing signed binaries to claim commercial readiness.

## Play Console
- App name and descriptions
- App icon / feature graphic / phone screenshots
- Privacy Policy URL: production-origin + /privacy
- Account deletion URL: production-origin + /account-deletion
- Data Safety questionnaire matched to enabled providers
- App access/reviewer instructions if OTP or restricted access blocks review
- Content rating questionnaire
- Ads declaration
- Target audience declaration
- Closed testing / production track as required for the developer account

## Launch blockers that must not be falsely marked complete
- Legal review status must be approved
- Real SMS must be configured
- Real payment provider must be configured
- Real KYC must be configured if required for withdrawals
- Production signing material must be present, safely backed up, and verified again for the exact public release
