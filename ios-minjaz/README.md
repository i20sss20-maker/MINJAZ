# MINJAZ for iPhone / iPad — SwiftUI beta

This is an actual iOS application source project, **not** an IPA, TestFlight release,
or App Store submission. It uses native SwiftUI discovery of all marketplace
categories and services, native navigation, share sheet, document picker,
download sharing, connection recovery, and authenticated first-party WebKit
workflows. All marketplace writes remain authorized by the existing server.

## Build

1. On a Mac with Xcode, install XcodeGen: `brew install xcodegen`.
2. Run `xcodegen generate --spec ios-minjaz/project.yml --project ios-minjaz`.
3. Open `ios-minjaz/Minjaz.xcodeproj` in Xcode.
4. Select **Debug** and an iOS 16+ simulator. Run the `Minjaz` scheme.
5. GitHub Actions workflow **MINJAZ iPhone and Android beta** also produces
   an unsigned, simulator-only `.app.zip`; it cannot be installed on a real iPhone.

### Environment isolation

| Xcode config | Bundle id | HTTPS origin |
| --- | --- | --- |
| Debug (simulator) | `sa.minjaz.preview` | `https://beta.minjazapp.com` |
| BetaRelease (physical iPhone) | `sa.minjaz.preview` | `https://beta.minjazapp.com` |
| Release | `sa.minjaz.app` | `https://minjaz-app-prod-production.up.railway.app` |

The app refuses unintended origins, keeps sessions in the persistent first-party
WebKit store, and opens external links in system apps. Do not change the Release
origin or ship a commercial build until the production backend and legal
readiness checks are approved.

### Before installing on a physical iPhone or sending to App Store Connect

- Apple Developer Program membership, the user's own Team ID, provisioning
  profile, signing certificate, and the final bundle identifier.
- A real 1024×1024 brand icon plus approved screenshots, privacy policy,
  support URL, accurate app privacy/data-use declaration and review notes.
- End-to-end human testing of customer and freelancer roles, account deletion,
  file upload/download and store payment boundaries.
- A reviewer-accessible verified demo account or approved demo mode.
- Public registration requires an approved mail sender/domain; the sandbox
  test sender may not deliver to arbitrary reviewers.
- App Review policy 4.2 requires meaningful app functionality beyond a
  simple repackaged web page. Native discovery/navigation is a first step,
  not a guarantee of App Review acceptance.
- Digital platform subscriptions/features may require StoreKit IAP.
  Payments for projects between clients and freelancers must be evaluated
  separately under current Apple policies. **No financial checkout or
  Apple Pay is enabled by this source.**

### Security

Do not embed `AUTH_SECRET`, payment provider tokens, backend credentials or
customer passwords. Do not activate direct production payments during
mobile-beta validation. iOS ATS enforces HTTPS; no unrestricted arbitrary
loads and no JavaScript auth bridge are used.

## Physical iPhone beta / TestFlight preparation

The new `BetaRelease` configuration enables a **separate, release-optimized iPhone
build that still points ONLY to the real MINJAZ sandbox**. It does not alter the
production `Release` bundle, payment settings or Railway. Runtime origin checks
are enforced by `MINJAZ_PREVIEW_BUILD` instead of assuming release implies production.

- Generate the source icon from the existing `public/icon.svg`: `python3 scripts/prepare_minjaz_ios_icon.py`.
  Requires `librsvg` (`brew install librsvg`) and Pillow (`python3 -m pip install pillow`).
  This produces a 1024px **opaque** PNG at `ios-minjaz/Sources/Assets.xcassets/AppIcon.appiconset/Minjaz-1024.png`.
  The generated PNG is ignored by Git and must be recreated before local builds.
- The **MINJAZ iPhone device beta (signed IPA)** GitHub Actions workflow is manual only.
  It requires typing `PREPARE_MINJAZ_IPA`; it does NOT push to TestFlight by itself.
- Configure GitHub Actions secrets (never commit them):
  `MINJAZ_IOS_TEAM_ID`, `MINJAZ_IOS_CERT_P12_BASE64`,
  `MINJAZ_IOS_CERT_PASSWORD`, `MINJAZ_IOS_PROFILE_BASE64`.
  The Apple Distribution .p12 and App Store distribution provisioning profile
  must belong to the **`sa.minjaz.preview`** App ID in your own Apple Developer team.
- The workflow validates the installed profile's team ID, app identifier,
  `get-task-allow=false`, expiry and distribution method *before* signing.
  It creates a temporary macOS keychain and removes both the keychain and
  embedded credentials at the end of the run. The artifact is a signed IPA
  (retained for 7 days), **not** an App Store submission.
- Set up the matching `sa.minjaz.preview` app record in App Store Connect.
  Upload the signed IPA using Transporter or Xcode after explicit approval,
  and add internal testers through TestFlight. Do not invite external testers
  without the appropriate beta review readiness.
- Full launch still requires approved legal text, mail sender, correct privacy
  disclosures, review credentials, actual customer/freelancer tests, account
  deletion, and properly classified IAP vs freelancer payouts. Signing is not
  proof of commercial readiness.

A real installable iPhone IPA cannot be produced until the **user's own**
distribution certificate, profile and team ID are supplied securely to CI.
No Apple signing identity is embedded in this repository.
