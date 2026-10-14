'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('android-preview/app/src/main/java/sa/minjaz/preview/MainActivity.java', 'utf8');
const gradle = fs.readFileSync('android-preview/app/build.gradle', 'utf8');

function region(start, end) {
  const a = source.indexOf(start);
  const b = source.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, 'Missing Android code region: ' + start);
  return source.slice(a, b);
}

const chooser = region('public boolean onShowFileChooser(', 'webView.setDownloadListener(');
assert.match(chooser, /finishFileChooser\(null\);\s*fileCallback = callback;/);
assert.match(chooser, /try\s*\{[\s\S]*params\.createIntent\(\)/);
assert.match(chooser, /startActivityForResult\(intent, FILE_CHOOSER_REQUEST\)/);
assert.match(chooser, /catch \(Exception e\)\s*\{\s*finishFileChooser\(null\);[\s\S]*return true;/);

const callback = region('private void finishFileChooser(Uri[] uris)', 'protected void onActivityResult(');
assert.match(callback, /ValueCallback<Uri\[\]> pending = fileCallback;\s*fileCallback = null;/);
assert.match(callback, /if \(pending != null\) pending\.onReceiveValue\(uris\);/);

const recovery = region('private void recoverWebView()', 'private void showLoading()');
assert.match(recovery, /cancelPageLoadTimeout\(\);[\s\S]*?finishFileChooser\(null\);/);
const result = region('protected void onActivityResult(', 'protected void onDestroy()');
assert.match(result, /finishFileChooser\(result\)/);
const destroy = region('protected void onDestroy()', 'private String localeCode()');
assert.match(destroy, /finishFileChooser\(null\)/);

const internal = region('private boolean isInternalUri(Uri uri)', 'private boolean handleNavigation(');
assert.match(internal, /uri\.getPort\(\) == -1 \|\| uri\.getPort\(\) == 443/);
assert.match(internal, /uri\.getUserInfo\(\) == null/);
const external = region('private boolean safeExternalUri(Uri uri)', 'private class MinjazWebViewClient');
assert.match(external, /uri\.getHost\(\) != null/);
assert.match(external, /if \(!safeExternalUri\(uri\)\) return;/);
for (const scheme of ['https', 'http', 'mailto', 'tel', 'sms', 'smsto', 'market', 'geo']) {
  assert.ok(external.includes('"' + scheme + '".equals(scheme)'), 'Missing allowlisted scheme: ' + scheme);
}
assert.match(gradle, /versionCode 13\s*versionName "1\.0\.0-rc3"/);
assert.match(gradle, /versionCode 12\s*versionName "0\.12-network-resilience"/);

// Test guards for network hand-offs and callbacks from destroyed WebViews.
const network = region('private void registerNetworkRecovery()', 'private void recoverWebView()');
assert.ok(network.includes('public void onCapabilitiesChanged(Network network, NetworkCapabilities capabilities)'));
assert.ok(network.includes('NetworkCapabilities.NET_CAPABILITY_VALIDATED'));
assert.ok(network.includes('mainHandler.removeCallbacks(pendingNetworkRetry)'));
assert.ok(network.includes('errorView.getVisibility() == View.VISIBLE && isNetworkReady()'));
assert.ok(network.includes('mainHandler.postDelayed(pendingNetworkRetry, 650)'));
const resume = region('protected void onResume()', 'protected void onPause()');
assert.ok(resume.includes('scheduleNetworkRetry()'));
assert.ok(destroy.includes('mainHandler.removeCallbacks(pendingNetworkRetry)'));
const webCallbacks = region('private class MinjazWebViewClient', 'private void registerNetworkRecovery()');
assert.ok(webCallbacks.split('if (view != webView) return;').length - 1 >= 5);
assert.ok(webCallbacks.includes('if (view == webView) recoverWebView();'));
console.log('MINJAZ_ANDROID_WEBVIEW_SAFETY_OK');
