'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const load = path => fs.readFileSync(path, 'utf8');
const nativeIos = load('ios-minjaz/Sources/MinjazNativeWorkspace.swift');
const appIos = load('ios-minjaz/Sources/MinjazApp.swift');
const nativeAndroid = load('android-preview/app/src/main/java/sa/minjaz/preview/NativeWorkspaceActivity.java');
const manifest = load('android-preview/app/src/main/AndroidManifest.xml');
const baseAndroid = load('android-preview/app/src/main/java/sa/minjaz/preview/MainActivity.java');

test('both apps have native marketplace workspaces, not a default embedded browser', () => {
  assert.match(appIos, /MinjazNativeScreen\(model: native, section: currentNativeSection/);
  assert.match(appIos, /if selected == \.discover \|\| selected == \.services/);
  assert.match(appIos, /\.sheet\(isPresented: \$showingWorkflow/);
  assert.match(appIos, /MinjazWebView\(browser: browser\)/);
  assert.match(manifest, /android:name="\.DiscoverActivity"\s+android:exported="true"[\s\S]*?android\.intent\.action\.MAIN/);
  assert.match(manifest, /android:name="\.NativeWorkspaceActivity"\s+android:exported="false"/);
  assert.match(manifest, /android:name="\.MainActivity"\s+android:exported="true"/);
  assert.match(baseAndroid, /new Intent\(this, NativeWorkspaceActivity\.class\)/);
  assert.match(nativeAndroid, /private void selectTab\(int tab\)/);
  assert.match(nativeAndroid, /startActivity\(new Intent\(this, DiscoverActivity\.class\)\)/);
});

test('only established server-owned data and role-scoped first-party endpoints appear', () => {
  for (const path of ['/api/v1/me','/api/v1/tasks','/api/v1/orders','/api/v1/conversations','/api/v1/notifications']) {
    assert.ok(nativeIos.includes(path), 'iOS missing '+path);
    assert.ok(nativeAndroid.includes(path), 'Android missing '+path);
  }
  assert.match(nativeIos, /get\("\/api\/v1\/me"\)/);
  assert.match(nativeAndroid, /readFirstParty\("\/api\/v1\/me"\)/);
  assert.match(nativeAndroid, /"client"\.equals\(accountRole\)/);
  assert.match(nativeIos, /account\?\.role == "freelancer"/);
  assert.doesNotMatch(nativeIos, /mockOrder|fakeProject|fakeOffers|storeKit.purchase/);
  assert.doesNotMatch(nativeAndroid, /mockOrder|fakeProject|fakeOffers|PAYMENT_MODE|RESEND_API_KEY/);
});

test('native reads never leak a verified-email session to a redirect or non-HTTPS origin', () => {
  assert.match(nativeIos, /cookie\.name == "minjaz_session" && cookie\.isSecure/);
  assert.match(nativeIos, /cookie\.domain\.trimmingCharacters/);
  assert.match(nativeIos, /WKWebsiteDataStore\.default\(\)\.httpCookieStore/);
  assert.match(nativeIos, /URLSessionConfiguration\.ephemeral/);
  assert.match(nativeIos, /completionHandler\(nil\)/);
  assert.match(nativeIos, /request\.httpMethod = "GET"/);
  assert.match(nativeIos, /config\.httpShouldSetCookies = false/);
  assert.match(nativeAndroid, /CookieManager\.getInstance\(\)\.getCookie\(BuildConfig\.APP_URL\)/);
  assert.match(nativeAndroid, /minjaz_session=\[\^;\]\+/);
  assert.match(nativeAndroid, /new URL\(target\.toString\(\)\)\.openConnection\(\)/);
  assert.match(nativeAndroid, /setInstanceFollowRedirects\(false\)/);
  assert.match(nativeAndroid, /setRequestMethod\("GET"\)/);
  assert.match(nativeAndroid, /if \(bytes\.size\(\) \+ n > MAX_BYTES\)/);
  assert.match(nativeAndroid, /status == 401/);
  assert.doesNotMatch(nativeAndroid, /setRequestMethod\("POST"\)|setRequestMethod\("PATCH"\)|setRequestMethod\("DELETE"\)/);
});

test('native screens have real account, empty, loading and explicit error states', () => {
  assert.match(nativeIos, /model\.loginRequired/);
  assert.match(nativeIos, /model\.isLoading/);
  assert.match(nativeIos, /model\.records\.isEmpty/);
  assert.match(nativeIos, /await model\.load\(section\)/);
  assert.match(nativeIos, /openWorkflow\("\/signup\?auth=login"\)/);
  assert.match(nativeAndroid, /catch \(SignInNeeded e\)/);
  assert.match(nativeAndroid, /native_signin_required/);
  assert.match(nativeAndroid, /native_load_failed/);
  assert.match(nativeAndroid, /executor\.shutdownNow\(\)/);
  assert.match(nativeAndroid, /generation == requestGeneration/);
  assert.match(nativeAndroid, /new Intent\(this, MainActivity\.class\)/);
});
