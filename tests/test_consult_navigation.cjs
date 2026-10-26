const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const detail = fs.readFileSync(path.join(root, 'farm_detail.html'), 'utf8');

function source(name) {
  const start = detail.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.ok(start >= 0);
  return detail.slice(start, detail.indexOf('\n}', start) + 2);
}

function setup(search = '') {
  const nodes = new Map();
  const element = id => {
    if (!nodes.has(id)) nodes.set(id, { value: '', innerHTML: '', hidden: false });
    return nodes.get(id);
  };
  const context = vm.createContext({
    URLSearchParams, location: { search },
    apiOk: false, apiList: [], apiSel: null, apiData: null, apiErr: null,
    apiRequestId: 0, detailMode: 'mock', page: 'detail', farms: [], selected: null,
    notices: [], toasts: [], boxes: [],
    document: { getElementById: element, querySelectorAll: () => [] },
    esc: value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    renderBrief() {},
  });
  context.addNotice = message => context.notices.push(message);
  context.toast = message => context.toasts.push(message);
  context.briefBoxes = (...html) => context.boxes.push(html);
  vm.runInContext(['initApi', 'loadApiDetail', 'renderPicker', 'renderApiDetail', 'saveApiLog']
    .map(source).join('\n'), context);
  return { context, element };
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('direct links select the requested household; missing IDs do not select another', async () => {
  for (const [search, expected] of [['?id=2', 2], ['?id=999', null], ['?id=bad', null], ['', 1]]) {
    const { context } = setup(search);
    context.apiGet = async () => [{ household_id: 1 }, { household_id: 2 }];
    await context.initApi();
    assert.equal(context.apiSel, expected);
    assert.equal(context.detailMode, 'api');
    if (expected === null) assert.ok(context.apiErr);
  }
});

test('empty lists and connection errors show an explicit state', async () => {
  const { context } = setup();
  context.apiGet = async () => [];
  await context.initApi();
  await context.renderApiDetail();
  assert.ok(context.boxes.at(-1)[0].includes('등록된 어가가 없어요'));
  context.apiGet = async () => { throw Error('HTTP 503'); };
  await context.initApi();
  await context.renderApiDetail();
  assert.equal(context.apiOk, false);
  assert.equal(context.apiSel, null);
  assert.ok(context.notices[0].includes('HTTP 503'));
  assert.ok(context.boxes.at(-1)[0].includes('HTTP 503'));
});

test('an older success or failure cannot overwrite the latest selection', async () => {
  for (const fail of [false, true]) {
    const { context } = setup();
    const old = deferred();
    context.detailMode = 'api';
    context.apiSel = 1;
    context.apiGet = url => url.includes('/1/') ? old.promise : Promise.resolve({ household: { household_id: 2 } });
    const pending = context.loadApiDetail(1);
    context.apiSel = 2;
    assert.equal(await context.loadApiDetail(2), true);
    if (fail) old.reject(Error('Old request failed'));
    else old.resolve({ household: { household_id: 1 } });
    assert.equal(await pending, false);
    assert.equal(context.apiData.household.household_id, 2);
    assert.equal(context.apiErr, null);
  }
});

test('a newer refresh of the same household supersedes an older request', async () => {
  const { context } = setup();
  const old = deferred();
  context.detailMode = 'api'; context.apiSel = 1;
  context.apiGet = () => old.promise;
  const pending = context.loadApiDetail(1, true);
  context.apiGet = async () => ({ household: { household_id: 1 }, version: 2 });
  await context.loadApiDetail(1, true);
  old.resolve({ household: { household_id: 1 }, version: 1 });
  assert.equal(await pending, false);
  assert.equal(context.apiData.version, 2);
});

test('saving is blocked when the displayed household differs from the selection', async () => {
  const { context } = setup();
  context.apiSel = 2; context.apiData = { household: { household_id: 1 } };
  let calls = 0;
  context.apiPost = async () => { calls++; };
  await context.saveApiLog();
  assert.equal(calls, 0);
  assert.equal(context.toasts.length, 1);
});

test('a save response cannot overwrite a newly selected household', async () => {
  const { context } = setup();
  const pending = deferred();
  context.detailMode = 'api'; context.apiSel = 1;
  context.apiData = { household: { household_id: 1 } };
  let target;
  context.apiPost = url => { target = url; return pending.promise; };
  const saving = context.saveApiLog();
  context.apiSel = 2;
  context.apiData = { household: { household_id: 2 } };
  pending.resolve({ consult: { status: 'saved' } });
  await saving;
  assert.equal(target, '/api/households/1/consult-logs');
  assert.equal(context.apiData.consult, undefined);
  assert.equal(context.toasts.length, 0);
});

test('consultation detail buttons navigate with an encoded household ID', () => {
  const html = fs.readFileSync(path.join(root, 'consult_status.html'), 'utf8');
  const start = html.indexOf("consultEl.addEventListener('click',");
  const handler = html.slice(start, html.indexOf('\n});', start) + 4);
  let click;
  const context = vm.createContext({
    encodeURIComponent, location: { href: '' },
    consultEl: { addEventListener: (event, callback) => { click = callback; } },
  });
  vm.runInContext(handler, context);
  click({ target: { closest: selector => selector === '[data-open]' ? { dataset: { open: '42&next=x' } } : null } });
  assert.equal(context.location.href, 'farm_detail.html?id=42%26next%3Dx');
});
