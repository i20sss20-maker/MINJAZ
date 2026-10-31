'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const read = path => fs.readFileSync(path, 'utf8');
const discovery = read('android-preview/app/src/main/java/sa/minjaz/preview/DiscoverActivity.java');
const main = read('android-preview/app/src/main/java/sa/minjaz/preview/MainActivity.java');
const manifest = read('android-preview/app/src/main/AndroidManifest.xml');
const preview = read('android-preview/app/build.gradle');
const ar = read('android-preview/app/src/main/res/values/strings.xml');
const en = read('android-preview/app/src/main/res/values-en/strings.xml');

test('native catalog is reachable internally, never as an external deep link', () => {
  assert.match(main, /startActivity\(new Intent\(MainActivity\.this, DiscoverActivity\.class\)\)/);
  assert.match(main, /root\.addView\(discover, discoverParams\)/);
  assert.match(manifest, /android:name="\.DiscoverActivity"\s+android:exported="false"/);
  assert.match(manifest, /android:name="\.MainActivity"\s+android:exported="true"/);
  assert.match(preview, /versionCode 16\s+versionName "0\.16-native-specialties-beta"/);
  assert.match(preview, /preview\s*\{[\s\S]*?APP_URL", '"https:\/\/beta\.minjazapp\.com\/workspace"'/);
});

test('native discovery only reads public first-party HTTPS JSON without web credentials', () => {
  assert.match(discovery, /"https"\.equalsIgnoreCase\(base\.getScheme\(\)\)/);
  assert.match(discovery, /base\.getUserInfo\(\) != null/);
  assert.match(discovery, /HttpsURLConnection/);
  assert.match(discovery, /setInstanceFollowRedirects\(false\)/);
  assert.match(discovery, /connection\.setRequestMethod\("GET"\)/);
  assert.match(discovery, /MAX_RESPONSE_BYTES/);
  assert.match(discovery, /readPublicApi\("\/api\/v1\/categories"\)/);
  assert.match(discovery, /readPublicApi\("\/api\/v1\/services"\)/);
  assert.doesNotMatch(discovery, /CookieManager|Authorization|setRequestProperty\("Cookie"|postData|evaluateJavascript|AUTH_SECRET|RESEND_API_KEY/);
});

test('catalog data are limited to returned active categories and matching services', () => {
  assert.match(discovery, /nextNames\.containsKey\(categoryId\)/);
  assert.match(discovery, /validId\(id\)/);
  assert.match(discovery, /private static boolean validId\(long id\)/);
  assert.match(discovery, /return id > 0 && id <= MAX_ID/);
  assert.match(discovery, /MAX_ID = 999999999999999L/);
  assert.match(discovery, /if \(!validId\(service\.id\) \|\| !validId\(service\.categoryId\)/);
});

test('only an explicit in-app selection can navigate to the role-aware workspace', () => {
  assert.match(discovery, /card\.setOnClickListener\(v -> openService\(service\)\)/);
  assert.match(discovery, /\.path\("\/workspace"\)\.clearQuery\(\)/);
  assert.match(discovery, /\.appendQueryParameter\("category_id", Long\.toString\(service\.categoryId\)\)/);
  assert.match(discovery, /\.appendQueryParameter\("service_id", Long\.toString\(service\.id\)\)/);
  assert.match(discovery, /new Intent\(this, MainActivity\.class\)/);
  assert.match(discovery, /Intent\.FLAG_ACTIVITY_CLEAR_TOP \| Intent\.FLAG_ACTIVITY_SINGLE_TOP/);
  assert.match(main, /if \(isInternalUri\(data\)\) \{\s*webView\.loadUrl\(localizedInternalUrl\(data\)\)/);
});

test('native discovery has paging, search, explicit error/retry and lifecycle cancellation', () => {
  assert.match(discovery, /visibleLimit = 40/);
  assert.match(discovery, /visibleLimit \+= 40/);
  assert.match(discovery, /search\.addTextChangedListener/);
  assert.match(discovery, /selectedCategory = id/);
  assert.match(discovery, /status\.setText\(R\.string\.discovery_connection_error\)/);
  assert.match(discovery, /executor\.shutdownNow\(\)/);
  assert.match(discovery, /generation == loadGeneration && !isFinishing\(\) && !isDestroyed\(\)/);
  for (const key of ['discovery_floating', 'discovery_title', 'discovery_search',
                     'discovery_connection_error', 'discovery_more', 'discovery_back']) {
    assert.match(ar, new RegExp('name="' + key + '"'));
    assert.match(en, new RegExp('name="' + key + '"'));
  }
});
