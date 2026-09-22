import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createApp, createGroupStates, handleMessage } from '../src/server.mjs';

const groups = createGroupStates();
const app = createApp(groups);
let server;
let baseUrl;

before(async () => {
  server = app.listen(0);
  await new Promise((resolve) => server.once('listening', resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(() => {
  server.close();
});

function attachFakeExtension(group, { delayMs = 0, responder } = {}) {
  const state = groups[group];
  let inFlight = 0;
  let maxConcurrent = 0;
  state.client = {
    readyState: 1,
    send(data) {
      const msg = JSON.parse(data);
      inFlight += 1;
      maxConcurrent = Math.max(maxConcurrent, inFlight);
      setTimeout(async () => {
        const result = await responder(msg);
        inFlight -= 1;
        handleMessage(group, JSON.stringify({ id: msg.id, result }), groups);
      }, delayMs);
    },
  };
  return { maxConcurrentRef: { get: () => maxConcurrent } };
}

const validBody = {
  title: '测试文章',
  content: '<p>正文</p>',
  markdown: '# 标题',
  platform: 'wechat',
  group: '2113',
  token: 'tok-1',
};

test('GET /health reports service and group ports', async () => {
  const res = await fetch(`${baseUrl}/health`);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.service, 'enterprise-kb-publisher-bridge');
  assert.equal(body.mode, 'resident-ws-gateway');
  assert.equal(Object.keys(body.group_ports).length, 4);
  assert.equal(body.group_ports['2113'].ws, 9531);
});

test('POST /api/publish rejects when required params are missing', async () => {
  const res = await fetch(`${baseUrl}/api/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'x' }),
  });
  assert.equal(res.status, 400);
  const body = await res.json();
  assert.equal(body.success, false);
  assert.match(body.error, /缺少必要参数/);
});

test('POST /api/publish rejects unknown account groups', async () => {
  const res = await fetch(`${baseUrl}/api/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...validBody, group: '9999' }),
  });
  assert.equal(res.status, 400);
  const body = await res.json();
  assert.equal(body.success, false);
  assert.match(body.error, /未知账号组/);
});

test('POST /api/publish returns failure when no extension is connected', async () => {
  groups['2113'].client = null;
  const res = await fetch(`${baseUrl}/api/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(validBody),
  });
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.success, false);
  assert.match(body.error, /Chrome 扩展未连接/);
});

test('POST /api/publish succeeds and returns the post URL', async () => {
  attachFakeExtension('2113', {
    responder: async (msg) => {
      assert.equal(msg.method, 'syncArticle');
      assert.equal(msg.token, 'tok-ok');
      assert.deepEqual(msg.params.platforms, ['wechat']);
      assert.equal(msg.params.article.title, '测试文章');
      return {
        results: [{ platform: 'wechat', success: true, postUrl: 'https://mp.weixin.qq.com/s/abc' }],
      };
    },
  });

  const res = await fetch(`${baseUrl}/api/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...validBody, token: 'tok-ok' }),
  });
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.success, true);
  assert.equal(body.url, 'https://mp.weixin.qq.com/s/abc');
});

test('POST /api/publish reports extension failure result', async () => {
  attachFakeExtension('2113', {
    responder: async () => ({
      results: [{ platform: 'wechat', success: false, error: '文章标题违规' }],
    }),
  });

  const res = await fetch(`${baseUrl}/api/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(validBody),
  });
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.success, false);
  assert.equal(body.error, '文章标题违规');
});

test('publishes to the same group are serialized (max 1 in-flight)', async () => {
  const tracker = attachFakeExtension('2113', {
    delayMs: 30,
    responder: async (msg) => ({
      results: [{ platform: 'wechat', success: true, postUrl: `https://x/${msg.token}` }],
    }),
  });

  const results = await Promise.all(
    ['a', 'b', 'c'].map((t) =>
      fetch(`${baseUrl}/api/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...validBody, token: t }),
      }).then((r) => r.json()),
    ),
  );

  assert.equal(tracker.maxConcurrentRef.get(), 1);
  for (const r of results) {
    assert.equal(r.success, true);
  }

  const health = await (await fetch(`${baseUrl}/health`)).json();
  assert.equal(health.queue_lengths['2113'], 0);
  assert.equal(health.running['2113'], false);
});

test('OPTIONS preflight returns 204 with CORS headers', async () => {
  const res = await fetch(`${baseUrl}/api/publish`, { method: 'OPTIONS' });
  assert.equal(res.status, 204);
  assert.equal(res.headers.get('access-control-allow-origin'), '*');
});
