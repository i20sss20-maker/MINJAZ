'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const workspace = fs.readFileSync(path.join(root, 'public/workspace-v1.js'), 'utf8');
const start = workspace.indexOf('let mobileServiceLinkApplied=false;');
const end = workspace.indexOf('async function loadCategories(){', start);
assert.ok(start > 0 && end > start, 'mobile handoff must run inside the real workspace source');
const handoff = workspace.slice(start, end);
const ios = fs.readFileSync(path.join(root, 'ios-minjaz/Sources/MinjazApp.swift'), 'utf8');

function run(search, role, specialties = [{ id: 24, category_id: 11, name_ar: 'تطوير المواقع' }]) {
  const controls = {};
  for (const key of ['categories', 'taskSubcategories', 'taskCategoryFilter',
                     'taskServiceFilter', 'create-section', 'tasks-section']) {
    controls[key] = { value: '', scrollIntoView() { state.scrolled.push(key); } };
  }
  const state = { notices: [], scrolled: [], locations: [], guidance: 0,
                  subcategories: 0, filters: 0 };
  const context = {
    URLSearchParams,
    window: { location: { search } },
    location: { pathname: '/workspace', search },
    marketplaceCategories: [{ id: 11, name_ar: 'التقنية' }],
    marketplaceSubcategories: specialties,
    currentUser: { role },
    $: id => controls[id],
    updateClientSubcategories() { state.subcategories++; },
    updateClientGuidance() { state.guidance++; },
    updateFreelancerTaskFilters() { state.filters++; },
    notice(message, kind) { state.notices.push({ message, kind }); },
    history: { replaceState(_data, _title, url) { state.locations.push(url); } },
    requestAnimationFrame(callback) { callback(); },
    TASK_PAGE_SIZE: 20,
    taskVisibleCount: 5
  };
  vm.createContext(context);
  vm.runInContext(handoff + '\napplyMobileServiceLink();applyMobileServiceLink();', context);
  return { controls, state, visible: context.taskVisibleCount };
}

test('iPhone selection carries its live specialty and category IDs to the server-backed workspace', () => {
  assert.match(ios, /service\.id > 0, service\.category_id > 0/);
  assert.match(ios, /workspace\?category_id=\\\(service\.category_id\)&service_id=\\\(service\.id\)/);
  assert.match(workspace, /applyMobileServiceLink\(\);\s*if\(currentUser\?\.role/);
});

test('client: selecting an active service prefills the real task form exactly once', () => {
  const { controls, state } = run('?category_id=11&service_id=24', 'client');
  assert.equal(controls.categories.value, '11');
  assert.equal(controls.taskSubcategories.value, '24');
  assert.equal(state.guidance, 1);
  assert.equal(state.subcategories, 1);
  assert.deepEqual(state.scrolled, ['create-section']);
  assert.equal(state.notices.length, 1);
  assert.equal(state.locations[0], '/workspace?category_id=11&service_id=24#create-section');
});

test('freelancer: link filters the existing real project list, never the create form', () => {
  const { controls, state, visible } = run('?category_id=11&service_id=24', 'freelancer');
  assert.equal(controls.taskCategoryFilter.value, '11');
  assert.equal(controls.taskServiceFilter.value, '24');
  assert.equal(state.filters, 1);
  assert.equal(state.subcategories, 0);
  assert.deepEqual(state.scrolled, ['tasks-section']);
  assert.equal(visible, 20);
});

test('rejects untrusted, duplicate, inactive or mismatched IDs without changing UI', () => {
  const bad = [
    '?category_id=11&service_id=25',
    '?category_id=12&service_id=24',
    '?category_id=11&service_id=24&service_id=24',
    '?category_id=11&category_id=11&service_id=24',
    '?category_id=-1&service_id=24',
    '?category_id=11&service_id=0',
    '?category_id=11&service_id=9007199254740999',
    '?category_id=11&service_id=24%3Cscript%3E',
    '?category_id=11&service_id=24.5'
  ];
  for (const query of bad) {
    const { controls, state } = run(query, 'client');
    assert.equal(controls.categories.value, '', query);
    assert.equal(controls.taskSubcategories.value, '', query);
    assert.deepEqual(state.scrolled, [], query);
    assert.deepEqual(state.notices, [], query);
  }
  const inactive = run('?category_id=11&service_id=24', 'client',
                       [{ id: 24, category_id: 12, name_ar: 'آخر' }]);
  assert.equal(inactive.controls.categories.value, '');
  assert.deepEqual(inactive.state.notices, []);
});

test('admin cannot prefill client or freelancer forms using a shared link', () => {
  const { controls, state } = run('?category_id=11&service_id=24', 'admin');
  assert.equal(controls.categories.value, '');
  assert.equal(controls.taskCategoryFilter.value, '');
  assert.equal(state.locations.length, 0);
});
