'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const file = path => fs.readFileSync(path, 'utf8');
const ios = file('ios-minjaz/Sources/MinjazApp.swift');
const catalog = file('ios-minjaz/Sources/MinjazCatalog.swift');
const browser = file('ios-minjaz/Sources/MinjazBrowser.swift');
const android = file('android-preview/app/src/main/java/sa/minjaz/preview/MainActivity.java');
const arabic = file('android-preview/app/src/main/res/values/strings.xml');
const english = file('android-preview/app/src/main/res/values-en/strings.xml');
const api = file('server.py');
const deletePage = file('public/account-deletion.html');

test('iPhone has native first-party account/privacy/deletion menu across every tab', () => {
  assert.match(ios, /@State private var showingAccountActions = false/);
  assert.match(ios, /Button \{ showingAccountActions = true \}/);
  assert.match(ios, /confirmationDialog\(/);
  for (const route of ['/signup?auth=login', '/workspace#profile', '/privacy', '/account-deletion']) {
    assert.ok(ios.includes('openAccountPage("'+route+'")'), 'Missing iOS route '+route);
  }
  assert.match(ios, /selected = \.account/);
  assert.match(ios, /if tab == \.account \{ accountSection = \.account \}/);
  assert.match(browser, /func open\(path: String\)/);
  assert.match(browser, /isFirstParty\(url\)/);
});

test('Android native account menu keeps its original authenticated WebView session', () => {
  assert.match(android, /private void showAccountMenu\(\)/);
  assert.match(android, /new AlertDialog\.Builder\(this\)/);
  assert.match(android, /account\.setOnClickListener\(v -> showAccountMenu\(\)\)/);
  assert.match(android, /header\.addView\(account, new LinearLayout\.LayoutParams\(/);
  assert.match(android, /root\.addView\(header, headerParams\)/);
  assert.match(android, /openInternalAccountPage\("\/signup", "auth", "login"\)/);
  for (const path of ['/workspace', '/privacy', '/account-deletion']) {
    assert.ok(android.includes('openInternalAccountPage("'+path+'", null, null)'));
  }
  const body = android.slice(android.indexOf('private void openInternalAccountPage('), android.indexOf('private View buildLoadingView()'));
  assert.match(body, /Uri\.parse\(APP_URL\)\.buildUpon\(\)/);
  assert.match(body, /if \(!isInternalUri\(target\)\) return/);
  assert.match(body, /webView\.loadUrl\(localizedInternalUrl\(target\)\)/);
  assert.doesNotMatch(body, /evaluateJavascript|CookieManager|clearCookies|setJavaScriptEnabled|loadDataWithBaseURL/);
  for (const key of ['account_floating','account_menu_title','account_login','account_profile','account_privacy','account_deletion']) {
    assert.ok(arabic.includes('name="'+key+'"'), 'Missing Arabic '+key);
    assert.ok(english.includes('name="'+key+'"'), 'Missing English '+key);
  }
});

test('privacy and deletion are live backend-managed, not fake or destructive native actions', () => {
  assert.match(api, /'\/privacy','\/privacy\.html','\/account-deletion','\/account-deletion\.html'/);
  assert.match(api, /'account_deletion_url':'\/account-deletion'/);
  assert.match(deletePage, /'\/api\/v1\/privacy\/requests'/);
  assert.match(deletePage, /request_type:'delete'/);
  assert.match(deletePage, /credentials:'same-origin'/);
  assert.match(deletePage, /confirmDelete/);
  assert.match(ios, /The backend verifies the active session/);
  assert.doesNotMatch(ios, /deleteAccount\(|eraseUserRecord\(|performImmediateDelete\(/);
});

test('iOS public catalog rejects cross-origin redirects, invalid IDs and category mismatches', () => {
  assert.match(catalog, /let finalURL = response\.url/);
  assert.match(catalog, /finalURL\.scheme == "https"/);
  assert.match(catalog, /finalURL\.host\?\.lowercased\(\) == origin\.host\?\.lowercased\(\)/);
  assert.match(catalog, /finalURL\.user == nil, finalURL\.password == nil/);
  assert.match(catalog, /categoryIDs\.contains\(item\.category_id\)/);
  assert.match(catalog, /serviceIDs\.insert\(item\.id\)\.inserted/);
  assert.match(catalog, /item\.id <= 999_999_999_999_999/);
  assert.match(catalog, /categories = Array\(validCategories\)/);
  assert.match(catalog, /services = Array\(validServices\)/);
});
