const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '..', 'demo', 'demo.js'), 'utf8');
function setup(saved = JSON.stringify({ enabled: true, offset: 8 })) {
  const calls = [], handlers = {};
  let reloads = 0;
  const context = vm.createContext({
    URL, Request, Response,
    localStorage: { getItem: () => saved },
    location: { origin: 'http://localhost:8000', href: 'http://localhost:8000/demo/consult_home.html', reload() { reloads++; } },
    document: { addEventListener: (name, handler) => { handlers[name] = handler; } },
    window: {
      fetch: async (input, options) => {
        calls.push({ url: input instanceof Request ? input.url : String(input), method: options?.method || input.method || 'GET' });
        return new Response('{}');
      },
      addEventListener: (name, handler) => { handlers[name] = handler; },
    },
  });
  vm.runInContext(source, context);
  return { context, calls, handlers, reloads: () => reloads };
}

test('기본값은 꺼짐이며 잘못된 저장값을 보정값으로 사용하지 않는다', () => {
  const data = { regions: [{ series: [{ max: 20, mean: 19, min: 18 }] }] };
  for (const saved of [null, 'bad', 'null', '{"enabled":true,"offset":99}', '{"enabled":true,"offset":0.25}']) {
    assert.equal(setup(saved).context.window.DemoSimulation.adjustRegions(data), data);
  }
});

test('예측 수온만 보정하고 원본·공식 특보는 보존한다', () => {
  const data = { regions: [{ alert: null, series: [{ max: 20, mean: 19, min: 18 }] }] };
  const s = setup();
  const adjusted = s.context.window.DemoSimulation.adjustRegions(data);
  assert.equal(adjusted.regions[0].series[0].max, 28);
  assert.equal(adjusted.regions[0].series[0].min, 26);
  assert.equal(data.regions[0].series[0].max, 20);
  assert.equal(adjusted.regions[0].alert, null);
});

test('어가 상세는 동일한 보정값으로 시연 전용 API를 사용한다', async () => {
  const s = setup();
  await s.context.window.fetch('/api/households/1/detail');
  assert.equal(s.calls[0].url, 'http://localhost:8000/demo/api/households/1/detail?offset=8');
  const off = setup('{"enabled":false,"offset":8}');
  await off.context.window.fetch('/api/households/1/detail');
  assert.match(off.calls[0].url, /offset=0$/);
});

test('실제 상담 저장·삭제는 서버로 보내지 않는다', async () => {
  const s = setup();
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    const response = await s.context.window.fetch('/api/consult/logs', { method });
    assert.equal(response.status, 403);
  }
  assert.equal(s.calls.length, 0);
});

test('계산 전용 POST와 원본 읽기 요청은 유지한다', async () => {
  const s = setup();
  await s.context.window.fetch('/api/households/1/claim-estimate', { method: 'POST', body: '{}' });
  await s.context.window.fetch('/api/consult/history');
  assert.match(s.calls[0].url, /\/demo\/api\/households\/1\/claim-estimate$/);
  assert.equal(s.calls[1].url, 'http://localhost:8000/api/consult/history');
});

test('Request 객체와 다른 탭의 시연 설정 변경도 처리한다', async () => {
  const s = setup();
  await s.context.window.fetch(new Request('http://localhost:8000/api/households/1/detail'));
  assert.match(s.calls[0].url, /offset=8$/);
  s.handlers.storage({ key: 'unrelated' });
  assert.equal(s.reloads(), 0);
  s.handlers.storage({ key: 'heat-dashboard-demo-temperature-v1' });
  assert.equal(s.reloads(), 1);
});
