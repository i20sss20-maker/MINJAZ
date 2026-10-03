# MINJAZ Google Play release checklist

## Android
- Production applicationId: sa.minjaz.app
- Preview applicationId: sa.minjaz.preview
- Production versionCode: 11
- Production versionName: 1.0.0-rc1
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
- Production signing secrets must exist
