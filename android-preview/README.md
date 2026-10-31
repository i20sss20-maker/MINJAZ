# MINJAZ Android preview

This module is the installable Android shell for the MINJAZ beta web application.

- applicationId: `sa.minjaz.preview`
- minSdk: 24
- targetSdk / compileSdk: 36
- preview version: `0.16-native-specialties-beta` (`versionCode 16`)
- production version remains `1.0.0-rc4` (`versionCode 14`) until intentionally approved
- form factors: phones, tablets, foldables, ChromeOS / resizable windows
- preview origin: `https://beta.minjazapp.com/workspace` (isolated sandbox)
- production origin (unchanged): `https://minjaz-app-prod-production.up.railway.app`
- each Android flavor has its own HTTPS deep-link host; preview must not access production.
- source and CI for iPhone/iPad are in `ios-minjaz/` and `.github/workflows/minjaz-mobile-beta.yml`.

Native Android specialty discovery is now accessible with the **استكشف التخصصات** button. It reads only the sandbox's public `/api/v1/categories` and `/api/v1/services` endpoints, searches and filters real specialties, and forwards the selected category/service pair to the existing client/freelancer workspace. Server-side role and data checks remain mandatory. Offline/error states show an explicit retry. Native discovery is preview-tested and not a replacement for authenticated forms.

The shell keeps first-party MINJAZ pages inside the app, opens external links with the system browser/app, supports file upload, restores WebView state after rotation/resize, handles system-bar insets, and shows a native retry screen for main-frame load failures.

The APK is a preview build. Production signing should use a stable private signing key before public release.

Compatibility-only v0.3 keeps the previous MINJAZ visual experience while updating Android platform support.

Runtime recovery v0.5 adds WebView crash recovery and automatic retry after connectivity returns, without changing the MINJAZ visual UI.

Release engineering v0.6 adds a non-debuggable release build and generates unsigned APK + AAB artifacts. Signing material must remain outside source control and be configured separately before Google Play submission.

Android v0.9 aligns the wrapper with MINJAZ Work Center v31, keeps external navigation isolated, downloads HTTPS attachments (including signed storage URLs) through Android DownloadManager, and shows the native retry screen for main-frame HTTP errors.

Android v0.10 adds a main-frame load watchdog, safer network recovery after resume, WebView renderer recovery, smarter back navigation (close overlays → home → native history), resize/orientation stability, and stricter artifact version checks.

### Account, privacy and deletion (Android 0.17 beta)

The native **حسابي والخصوصية** button opens first-party login, profile,
privacy policy and the existing authenticated account-deletion request page.
It never sends, stores or logs credentials. Account deletion is **requested**
from the protected backend and is not silently executed by tapping the menu.
All pages retain the original WebView session, verified email checks and
backend permissions. Nothing here enables production payments.
