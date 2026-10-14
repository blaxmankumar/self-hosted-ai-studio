import test from 'node:test';
import assert from 'node:assert/strict';
import { backendConfiguration, permittedPath, forwardToBackend } from '../lib/local-backend.mjs';

const ID = '12345678-1234-1234-1234-123456789abc';
const req = (path = 'health', init) => new Request(`http://127.0.0.1:3000/api/local/${path}`, init);
const payload = { model: 'missing', prompt: 'a custom scene' };
const post = (body = JSON.stringify(payload), headers = {}) => req('generate/image', {
  method: 'POST', body, headers: { 'content-type': 'application/json', ...headers },
});

test('loopback configuration rejects remote, credential-bearing and malformed endpoints', () => {
  assert.equal(backendConfiguration({}).origin, 'http://127.0.0.1:8000');
  assert.equal(backendConfiguration({ LOCAL_BACKEND_URL: 'http://localhost:9000' }).origin, 'http://127.0.0.1:9000');
  for (const url of ['https://api.muapi.ai', 'http://example.com', 'http://127.0.0.1.evil.test', 'http://user:secret@127.0.0.1:8000', 'http://127.0.0.1:8000/path', 'http://127.0.0.1:8000/?x=1']) {
    assert.throws(() => backendConfiguration({ LOCAL_BACKEND_URL: url }));
  }
  assert.throws(() => backendConfiguration({ LOCAL_BACKEND_TIMEOUT_MS: '0' }));
});

test('only supported endpoints and safe UUID output paths are accepted', () => {
  assert.equal(permittedPath('GET', ['jobs', ID]), `jobs/${ID}`);
  assert.equal(permittedPath('GET', ['outputs', ID, 'result.png']), `outputs/${ID}/result.png`);
  for (const path of [['outputs', ID, '..'], ['outputs', ID, 'a/b.png'], ['outputs', ID, 'page.html'], ['jobs', 'old-remote-job'], ['https:', '', 'api.muapi.ai']]) {
    assert.equal(permittedPath('GET', path), null);
  }
  assert.equal(permittedPath('POST', ['health']), null);
});

test('generation forwarding never copies credentials or key headers', async () => {
  const request = post(undefined, { origin: 'http://127.0.0.1:3000', 'x-api-key': 'stale-secret', authorization: 'Bearer stale-secret', cookie: 'secret=1' });
  let observed;
  const response = await forwardToBackend(request, ['generate', 'image'], { env: {}, fetchImpl: async (url, options) => {
    observed = { url, options };
    return Response.json({ error: { code: 'MODEL_NOT_AVAILABLE', message: 'Install a model first.' } }, { status: 409 });
  } });
  assert.equal(response.status, 409);
  assert.equal(observed.url, 'http://127.0.0.1:8000/generate/image');
  assert.deepEqual(JSON.parse(observed.options.body), payload);
  assert.deepEqual(observed.options.headers, { 'Content-Type': 'application/json', Accept: 'application/json' });
  assert.equal(observed.options.redirect, 'error');
});

test('cross-site requests, upload bodies and invalid payloads never reach backend', async () => {
  let calls = 0;
  const opts = { env: {}, fetchImpl: async () => { calls++; return Response.json({}); } };
  assert.equal((await forwardToBackend(post(undefined, { origin: 'https://other.test' }), ['generate', 'image'], opts)).status, 403);
  assert.equal((await forwardToBackend(req('uploads', { method: 'POST', body: 'media' }), ['uploads'], opts)).status, 501);
  assert.equal((await forwardToBackend(post('invalid'), ['generate', 'image'], opts)).status, 422);
  assert.equal((await forwardToBackend(post('[]'), ['generate', 'image'], opts)).status, 422);
  assert.equal((await forwardToBackend(post('x'.repeat(65537)), ['generate', 'image'], opts)).status, 413);
  assert.equal((await forwardToBackend(post('{}', { 'content-type': 'text/plain' }), ['generate', 'image'], opts)).status, 415);
  assert.equal(calls, 0);
});

test('offline backend, timeouts and malformed config produce actionable errors', async () => {
  for (const [name, status, code] of [['TypeError', 503, 'BACKEND_UNAVAILABLE'], ['TimeoutError', 504, 'BACKEND_TIMEOUT']]) {
    const response = await forwardToBackend(req(), ['health'], { env: {}, fetchImpl: async () => { const error = new Error('network'); error.name = name; throw error; } });
    assert.equal(response.status, status);
    assert.equal((await response.json()).error.code, code);
  }
  let calls = 0;
  const response = await forwardToBackend(req(), ['health'], { env: { LOCAL_BACKEND_URL: 'http://example.com' }, fetchImpl: async () => { calls++; } });
  assert.equal(response.status, 503);
  assert.equal(calls, 0);
});

test('output forwarding preserves bytes and rejects executable response types', async () => {
  const response = await forwardToBackend(req(`outputs/${ID}/result.png`), ['outputs', ID, 'result.png'], { env: {}, fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-type': 'image/png' } }) });
  assert.deepEqual([...new Uint8Array(await response.arrayBuffer())], [1, 2, 3]);
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  const invalid = await forwardToBackend(req(), ['health'], { env: {}, fetchImpl: async () => new Response('<script></script>', { headers: { 'content-type': 'text/html' } }) });
  assert.equal(invalid.status, 502);
});
