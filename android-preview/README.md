# MINJAZ Android preview

This module is the installable Android shell for the MINJAZ beta web application.

- applicationId: `sa.minjaz.preview`
- minSdk: 24
- targetSdk / compileSdk: 36
- version: `0.2-device-support`
- form factors: phones, tablets, foldables, ChromeOS / resizable windows
- production URL: `https://minjaz-app-prod-production.up.railway.app`

The shell keeps first-party MINJAZ pages inside the app, opens external links with the system browser/app, supports file upload, restores WebView state after rotation/resize, handles system-bar insets, and shows a native retry screen for main-frame load failures.

The APK is a preview build. Production signing should use a stable private signing key before public release.
