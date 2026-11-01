'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const read = x => fs.readFileSync(x,'utf8');
const manifest = read('android-preview/app/src/main/AndroidManifest.xml');
const android = read('android-preview/app/src/main/java/sa/minjaz/preview/DiscoverActivity.java');
const ios = read('ios-minjaz/Sources/MinjazCatalog.swift');
const detail = read('ios-minjaz/Sources/MinjazSpecialtyDetails.swift');
const gradle = read('android-preview/app/build.gradle');
const docker = read('.dockerignore');

test('native Android opens public Explore first and keeps login behind authenticated workflow', () => {
  assert.match(manifest, /android:name="\.DiscoverActivity"\s+android:exported="true"[\s\S]*?android\.intent\.action\.MAIN/);
  assert.match(manifest, /android:name="\.NativeWorkspaceActivity"\s+android:exported="false"/);
  assert.match(android, /addNativeBottomNavigation\(\)/);
  assert.match(android, /int\[\] labels = \{R\.string\.nav_discover, R\.string\.nav_projects, R\.string\.nav_orders/);
  assert.match(android, /item\.setOnClickListener\(v -> \{ if \(!active\) openNativeTab\(tab\); \}\)/);
  assert.match(android, /Intent intent = new Intent\(this, NativeWorkspaceActivity\.class\)/);
  assert.match(android, /intent\.putExtra\("minjaz_tab", tab\)/);
  assert.match(android, /startActivity\(intent\);\s*finish\(\)/);
});

test('native specialty details are real server content, user action still role guarded', () => {
  assert.match(ios, /@State private var chosenService: MinjazService\?/);
  assert.match(ios, /\.sheet\(item: \$chosenService, onDismiss:/);
  assert.match(ios, /MinjazSpecialtyDetails\(/);
  assert.match(ios, /pendingOpen = service\s*chosenService = nil/);
  assert.match(detail, /client_guidance/);
  assert.match(detail, /freelancer_guidance/);
  assert.match(detail, /Text\("متابعة إلى المشروع"\)/);
  assert.match(android, /row\.optString\("client_guidance", ""\)/);
  assert.match(android, /new AlertDialog\.Builder\(this\)/);
  assert.match(android, /\.setPositiveButton\(R\.string\.discovery_detail_continue/);
  assert.match(android, /private void continueToService\(Service service\)/);
  assert.match(android, /\.path\("\/workspace"\)\.clearQuery\(\)/);
  assert.match(android, /setRequestMethod\("GET"\)/);
  assert.doesNotMatch(android, /setRequestMethod\("POST"\)/);
});

test('0.21 ships from guarded preview and Python image ignores mobile build sources', () => {
  assert.match(gradle, /versionCode 21\s+versionName "0\.21-native-discovery-beta"/);
  assert.match(docker, /^ios-minjaz\/$/m);
  assert.match(docker, /^android-preview\/$/m);
  assert.doesNotMatch(docker, /^public\/$/m);
  assert.doesNotMatch(docker, /^tests\/$/m);
});
