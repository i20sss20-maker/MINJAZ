'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const read = path => fs.readFileSync(path, 'utf8');
const android = read('android-preview/app/src/main/java/sa/minjaz/preview/MainActivity.java');
const ios = read('ios-minjaz/Sources/MinjazApp.swift');
const browser = read('ios-minjaz/Sources/MinjazBrowser.swift');
const ar = read('android-preview/app/src/main/res/values/strings.xml');
const en = read('android-preview/app/src/main/res/values-en/strings.xml');
const gradle = read('android-preview/app/build.gradle');

test('Android five-tab navigation is native and keeps WebView within safe content bounds', () => {
  assert.match(android, /private FrameLayout\.LayoutParams browserContentParams\(\)/);
  assert.match(android, /p\.topMargin = dp\(58\)/);
  assert.match(android, /p\.bottomMargin = dp\(70\)/);
  assert.match(android, /webView\.setLayoutParams\(browserContentParams\(\)\)/);
  assert.match(android, /root\.addView\(loadingView, browserContentParams\(\)\)/);
  assert.match(android, /root\.addView\(errorView, browserContentParams\(\)\)/);
  assert.match(android, /root\.addView\(header, headerParams\)/);
  assert.match(android, /root\.addView\(bottomNav, bottomParams\)/);
  assert.match(android, /int\[\] labels = \{R\.string\.nav_discover, R\.string\.nav_projects, R\.string\.nav_orders,/);
  assert.match(android, /R\.string\.nav_services, R\.string\.nav_account/);
  assert.match(android, /new LinearLayout\.LayoutParams\(\s*0, ViewGroup\.LayoutParams\.MATCH_PARENT, 1\)/);
  assert.doesNotMatch(android, /root\.addView\(discover, discoverParams\)/);
  assert.doesNotMatch(android, /root\.addView\(account, accountParams\)/);
  for (const key of ['nav_discover','nav_projects','nav_orders','nav_services','nav_account']) {
    assert.ok(ar.includes('name="'+key+'"'));
    assert.ok(en.includes('name="'+key+'"'));
  }
});

test('real native tabs navigate to the matching first-party routes, never fake data', () => {
  assert.match(android, /private void navigateNativeTab\(int tab\)/);
  assert.match(android, /startActivity\(new Intent\(MainActivity\.this, DiscoverActivity\.class\)\)/);
  assert.match(android, /new Intent\(this, NativeWorkspaceActivity\.class\)/);
  assert.match(android, /intent\.putExtra\("minjaz_tab", tab\)/);
  assert.match(android, /Uri\.parse\(APP_URL\)\.buildUpon\(\)/);
  assert.match(android, /if \(!isInternalUri\(target\)\) return/);
  assert.match(android, /webView\.loadUrl\(localizedInternalUrl\(target\)\)/);
  assert.match(android, /syncSelectedTab\(url\)/);
  assert.match(android, /root\.addView\(webView, 0\)/);
  assert.match(android, /pageHasRendered = false/);
  assert.match(android, /pageHasRendered = true/);
  assert.match(android, /pageHasRendered \? View\.GONE : View\.VISIBLE/);
  assert.match(gradle, /versionCode 19\s*versionName "0\.19-native-workspace-beta"/);
});

test('iPhone uses real brand accents, accessibility labels and nonblocking loading', () => {
  assert.match(ios, /Color\(red: 101\/255, green: 88\/255, blue: 245\/255\)/);
  assert.match(ios, /Image\(systemName: "square\.stack\.3d\.up\.fill"\)/);
  assert.doesNotMatch(ios, /Image\(systemName: "checkmark\.seal\.fill"\)/);
  assert.match(ios, /ZStack\(alignment: \.top\)/);
  assert.match(ios, /ProgressView\(\)\s*\.progressViewStyle\(\.linear\)/);
  assert.doesNotMatch(ios, /Text\("جاري فتح مِنجاز…"\)/);
  assert.match(ios, /\.accessibilityLabel\(tab\.title\)/);
  assert.match(ios, /ForEach\(MobileTab\.allCases\)/);
  assert.match(ios, /MinjazNativeScreen\(model: native, section: currentNativeSection/);
  assert.match(ios, /openWorkflow\(path\)/);
  assert.match(ios, /showingWorkflow = true/);
});

test('native iPhone pull-to-refresh terminates for all supported outcomes', () => {
  assert.match(browser, /private let pullToRefresh = UIRefreshControl\(\)/);
  assert.match(browser, /webView\.scrollView\.refreshControl = pullToRefresh/);
  assert.match(browser, /#selector\(refreshFromGesture\)/);
  assert.match(browser, /@objc private func refreshFromGesture\(\)/);
  assert.match(browser, /func reload\(\)/);
  assert.match(browser, /pullToRefresh\.endRefreshing\(\)/);
  const events = [
    'didFinish navigation:',
    'didFailProvisionalNavigation navigation:',
    'didFail navigation:',
    'webViewWebContentProcessDidTerminate'
  ];
  for (const event of events) {
    const index = browser.indexOf(event);
    assert.ok(index >= 0, 'Missing browser callback '+event);
    assert.match(browser.slice(index,index+300), /stopRefreshing\(\)/, 'No end refresh in '+event);
  }
  assert.match(browser, /http\.statusCode >= 500[\s\S]*stopRefreshing\(\)/);
});
