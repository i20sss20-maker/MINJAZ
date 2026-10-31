'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const read = f => fs.readFileSync(f, 'utf8');
const swift = read('ios-minjaz/Sources/MinjazApp.swift');
const swiftCatalog = read('ios-minjaz/Sources/MinjazCatalog.swift');
const swiftTheme = read('ios-minjaz/Sources/MinjazDesignSystem.swift');
const javaStyle = read('android-preview/app/src/main/java/sa/minjaz/preview/MinjazStyle.java');
const javaDiscover = read('android-preview/app/src/main/java/sa/minjaz/preview/DiscoverActivity.java');
const javaWorkspace = read('android-preview/app/src/main/java/sa/minjaz/preview/NativeWorkspaceActivity.java');
const javaWeb = read('android-preview/app/src/main/java/sa/minjaz/preview/MainActivity.java');
const ar = read('android-preview/app/src/main/res/values/strings.xml');
const en = read('android-preview/app/src/main/res/values-en/strings.xml');
const gradle = read('android-preview/app/build.gradle');

test('brand palette, accessible Arabic type and real logo are used throughout iPhone', () => {
  for (const color of ['primary','deep','ink','muted','canvas','tinted','border']) {
    assert.match(swiftTheme, new RegExp('static let ' + color + ' = Color'));
  }
  assert.match(swiftTheme, /struct MinjazBrandMark: View/);
  assert.match(swiftTheme, /struct MinjazSurface<Content: View>: View/);
  assert.match(swiftTheme, /Arabic text shaping and Dynamic Type/);
  assert.match(swift, /MinjazBrandMark\(dimension: 38\)/);
  assert.match(swift, /MinjazUI\.body\(11, weight: selected == tab \? \.bold : \.medium\)/);
  assert.match(swiftCatalog, /Text\("تخصصات تناسب مشروعك"\)/);
  assert.match(swiftCatalog, /TextField\("ابحث في التخصصات", text: \$keyword\)/);
  assert.match(swiftCatalog, /sectionHeading\("الأقسام الرئيسية"\)/);
  assert.match(swiftCatalog, /LazyVStack\(spacing: 10\)/);
  assert.match(swiftCatalog, /\.lineLimit\(1\)[\s\S]*?\.fixedSize\(horizontal: true, vertical: false\)/);
  assert.match(swiftCatalog, /categoryButton\(category\.id, name: category\.name_ar\)/);
  assert.match(swiftCatalog, /Button \{ chosenService = service \}/);
  assert.match(swiftCatalog, /onOpen\(service\)/);
  assert.doesNotMatch(swiftCatalog, /https?:\/\/(?:placehold|fake|lorem)/);
});

test('Android app uses drawn vector icons and readable text rather than font glyphs and emoji', () => {
  assert.match(javaStyle, /class Glyph extends View/);
  assert.match(javaStyle, /Canvas canvas/);
  assert.match(javaStyle, /Typeface\.create\("sans-serif"/);
  for (const s of ['GRID','BRIEFCASE','INBOX','SERVICES','USER','SEARCH','CHEVRON','MARK']) {
    assert.match(javaStyle, new RegExp('case ' + s + ':|\\b' + s + ' ='));
  }
  assert.match(javaDiscover, /MinjazStyle\.icon\(this, MinjazStyle\.MARK, VIOLET\)/);
  assert.match(javaDiscover, /MinjazStyle\.icon\(this, MinjazStyle\.SEARCH, VIOLET\)/);
  assert.match(javaDiscover, /MinjazStyle\.icon\(this, MinjazStyle\.BRIEFCASE, VIOLET\)/);
  assert.match(javaDiscover, /MinjazStyle\.text\(view, bold\)/);
  assert.match(javaDiscover, /chip\.setSingleLine\(true\)/);
  assert.match(javaDiscover, /card\.setOnClickListener\(v -> openService\(service\)\)/);
  assert.match(javaWorkspace, /MinjazStyle\.icon\(this, MinjazStyle\.MARK, PURPLE\)/);
  assert.match(javaWorkspace, /MinjazStyle\.Glyph/);
  assert.match(javaWeb, /MinjazStyle\.Glyph\[\] navIcons/);
  assert.doesNotMatch(javaWeb, /String\[\] glyphs = \{"⌕"/);
  assert.doesNotMatch(javaWorkspace, /String\[\] icons = \{"⌕"/);
  assert.match(ar, /<string name="discovery_categories">الأقسام الرئيسية<\/string>/);
  assert.match(en, /<string name="discovery_categories">Main categories<\/string>/);
  assert.match(gradle, /versionCode 21\s*versionName "0\.21-native-discovery-beta"/);
});

test('native screenshots show real API data and cannot bypass marketplace rules', () => {
  assert.match(javaDiscover, /readPublicApi\("\/api\/v1\/services"\)/);
  assert.match(javaDiscover, /readPublicApi\("\/api\/v1\/categories"\)/);
  assert.match(javaDiscover, /new Intent\(this, MainActivity\.class\)/);
  assert.match(swiftCatalog, /get\("\/api\/v1\/categories", origin: origin\)/);
  assert.match(swiftCatalog, /get\("\/api\/v1\/services", origin: origin\)/);
  assert.match(swiftCatalog, /service\.category_id/);
  assert.doesNotMatch(javaDiscover, /setRequestMethod\("POST"\)/);
});
