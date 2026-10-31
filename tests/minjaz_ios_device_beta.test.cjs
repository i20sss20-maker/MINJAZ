'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const read = path => fs.readFileSync(path, 'utf8');
const project = read('ios-minjaz/project.yml');
const browser = read('ios-minjaz/Sources/MinjazBrowser.swift');
const workflow = read('.github/workflows/minjaz-ios-device-beta.yml');
const mainCI = read('.github/workflows/minjaz-mobile-beta.yml');
const generator = read('scripts/prepare_minjaz_ios_icon.py');
const plist = read('ios-minjaz/Sources/Info.plist');
const icon = JSON.parse(read('ios-minjaz/Sources/Assets.xcassets/AppIcon.appiconset/Contents.json'));

test('iOS physical beta remains separate from protected production bundle and host', () => {
  assert.match(project, /configs:\s+Debug: debug\s+BetaRelease: release\s+Release: release/);
  const beta = project.match(/        BetaRelease:\n([\s\S]*?)        Release:/);
  const prod = project.match(/        Release:\n([\s\S]*?)\n    scheme:/);
  assert.ok(beta && prod);
  assert.match(beta[1], /PRODUCT_BUNDLE_IDENTIFIER: sa\.minjaz\.preview/);
  assert.match(beta[1], /MINJAZ_BASE_URL: 'https:\/\/beta\.minjazapp\.com'/);
  assert.match(beta[1], /SWIFT_ACTIVE_COMPILATION_CONDITIONS: 'MINJAZ_PREVIEW_BUILD'/);
  assert.match(prod[1], /PRODUCT_BUNDLE_IDENTIFIER: sa\.minjaz\.app/);
  assert.match(prod[1], /MINJAZ_BASE_URL: 'https:\/\/minjaz-app-prod-production\.up\.railway\.app'/);
  assert.match(browser, /#if MINJAZ_PREVIEW_BUILD/);
  assert.match(browser, /precondition\(host == "beta\.minjazapp\.com"/);
  assert.match(browser, /#else\s+precondition\(host == "minjaz-app-prod-production\.up\.railway\.app"/);
  assert.match(project, /ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon/);
  assert.match(project, /INFOPLIST_FILE: Sources\/Info\.plist/);
  assert.match(project, /GENERATE_INFOPLIST_FILE: NO/);
  assert.doesNotMatch(project, /^    info:/m, 'XcodeGen must never overwrite the checked-in plist');
  assert.match(plist, /<key>MinjazBaseURL<\/key>/);
  assert.match(plist, /<string>\$\(MINJAZ_BASE_URL\)<\/string>/);
  for (const key of ['CFBundleIdentifier','CFBundleExecutable','CFBundlePackageType','CFBundleName',
                     'CFBundleShortVersionString','CFBundleVersion']) {
    assert.match(plist, new RegExp('<key>'+key+'</key>'));
  }
});

test('iPhone profile signing is human-triggered, manual, beta-only, no automatic upload', () => {
  assert.match(workflow, /workflow_dispatch:\s+inputs:/);
  assert.doesNotMatch(workflow, /^\s{2}push:/m);
  assert.doesNotMatch(workflow, /^\s{2}pull_request:/m);
  assert.match(workflow, /github\.ref == 'refs\/heads\/feature\/digital-services-geidea-sandbox'/);
  assert.match(workflow, /inputs\.confirm == 'PREPARE_MINJAZ_IPA'/);
  assert.match(workflow, /runs-on: macos-26/);
  assert.match(workflow, /environment: minjaz-ios-beta/);
  assert.match(workflow, /MINJAZ_IOS_CERT_P12_BASE64/);
  assert.match(workflow, /MINJAZ_IOS_CERT_PASSWORD/);
  assert.match(workflow, /MINJAZ_IOS_PROFILE_BASE64/);
  assert.match(workflow, /MINJAZ_IOS_TEAM_ID/);
  assert.match(workflow, /APP_IDENTIFIER.*TEAM_ID\.sa\.minjaz\.preview/);
  assert.match(workflow, /ALLOW_DEBUG.*false/);
  assert.match(workflow, /not p\.get\('ProvisionedDevices'\)/);
  assert.match(workflow, /Expired provisioning profile/);
  assert.match(workflow, /CODE_SIGN_STYLE=Manual/);
  assert.match(workflow, /-configuration BetaRelease/);
  assert.match(workflow, /'destination':'export'/);
  assert.doesNotMatch(workflow, /'destination':'upload'/);
  assert.doesNotMatch(workflow, /altool --upload-app|transporter upload|fastlane pilot upload/);
  assert.match(workflow, /-exportArchive/);
  assert.match(workflow, /delete-keychain/);
  assert.match(workflow, /MINJAZ-iPhone-physical-beta-SIGNED-IPA/);
});

test('official vector icon is generated as a real opaque 1024px marketing asset', () => {
  assert.equal(icon.images.length, 1);
  assert.equal(icon.images[0].filename, 'Minjaz-1024.png');
  assert.equal(icon.images[0].size, '1024x1024');
  assert.match(generator, /public" \/ "icon.svg"/);
  assert.match(generator, /1024, 1024/);
  assert.match(generator, /Image\.new\("RGB"/);
  assert.match(generator, /"rsvg-convert"/);
  assert.match(generator, /check\.mode != "RGB"/);
  assert.match(read('.gitignore'), /ios-minjaz\/Sources\/Assets\.xcassets\/AppIcon\.appiconset\/Minjaz-1024\.png/);
  assert.match(mainCI, /python3 scripts\/prepare_minjaz_ios_icon\.py/);
});
