'use strict';
// Isolate MINJAZ's real navigation-loading wrapper in a mocked DOM.
// Ensures slow and overlapping requests never lock the controls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('public/index.html', 'utf8');
assert.match(html, /\.page\.rcLoading\{[^}]*pointer-events:auto/);
const start = html.indexOf('let pageBusyWatchdog=null;');
const end = html.indexOf(' // Keep desktop navigation complete', start);
assert.ok(start >= 0 && end > start, 'navigation loading wrapper must exist');
const source = html.slice(start, end);

function element(initial = []) {
  const classes = new Set(initial);
  return {
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      contains: name => classes.has(name),
    },
    setAttribute(name, value) { this[name] = value; },
    textContent: '',
  };
}

const loading = element(['hidden']);
const loadingText = element();
const home = element(['page']);
const orders = element(['page']);
const tasks = element(['page']);
const nodes = {pageLoading: loading, pageLoadingText: loadingText, home, orders, tasks};
const scheduled = new Map();
const pending = [];
let nextTimer = 0;
const win = {
  go: id => new Promise(resolve => pending.push({id, resolve})),
  scrollTo() {},
};
const context = {
  window: win,
  currentPage: 'home',
  pageLoadSeq: 0,
  history: {replaceState() {}},
  document: {
    getElementById: id => nodes[id] || null,
    querySelectorAll: selector => selector === '.page' ? [home, orders, tasks] : [],
  },
  setTimeout: (fn, delay) => {const id = ++nextTimer; scheduled.set(id, {fn, delay}); return id;},
  clearTimeout: id => scheduled.delete(id),
};
vm.runInNewContext(source, context);

async function run() {
  const first = win.go('home');
  assert.equal(loading.classList.contains('hidden'), false);
  assert.equal(home.classList.contains('rcLoading'), true);
  assert.equal(scheduled.size, 1);

  // An older request completing cannot hide the newer route's spinner.
  context.currentPage = 'orders';
  const second = win.go('orders');
  assert.equal(home.classList.contains('rcLoading'), false);
  assert.equal(orders.classList.contains('rcLoading'), true);
  pending[0].resolve();
  await first;
  assert.equal(loading.classList.contains('hidden'), false);
  pending[1].resolve();
  await second;
  assert.equal(loading.classList.contains('hidden'), true);
  assert.equal(orders.classList.contains('rcLoading'), false);
  assert.equal(scheduled.size, 0);

  // A stalled request releases the busy state after the watchdog fires.
  context.currentPage = 'tasks';
  const stalled = win.go('tasks');
  const watchdog = [...scheduled.values()].find(x => x.delay === 8000);
  assert.ok(watchdog, 'navigation watchdog must have an 8-second deadline');
  watchdog.fn();
  assert.equal(loading.classList.contains('hidden'), true);
  assert.equal(tasks.classList.contains('rcLoading'), false);
  pending[2].resolve();
  await stalled;
  assert.equal(scheduled.size, 0);
  console.log('MINJAZ_NAVIGATION_LOADING_SAFETY_OK');
}
run().catch(error => {console.error(error); process.exitCode = 1;});
